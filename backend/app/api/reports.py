import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Arrival, BunchReport, Line, Trip, TripHold
from app.services.bunch_engine import apply_holds, detect_bunching, events_to_dicts
router = APIRouter(prefix="/reports", tags=["reports"])

def _hold_map(db: Session, trip_ids: list[int], trip_no_map: dict[int, str]) -> dict[tuple[str, str], float]:
    """{(trip_no, stop_name): hold_minutes},只含有效登记(>0)。"""
    if not trip_ids: return {}
    rows = db.scalars(select(TripHold).where(TripHold.trip_id.in_(trip_ids))).all()
    return {(trip_no_map[h.trip_id], h.stop_name): h.hold_minutes for h in rows
            if h.trip_id in trip_no_map and h.hold_minutes > 0}

@router.get("")
def list_reports(db: Session = Depends(get_db)):
    rows = db.scalars(select(BunchReport).order_by(BunchReport.id.desc())).all()
    return [{"id": r.id, "line_id": r.line_id, "stop_name": r.stop_name,
             "created_at": r.created_at.isoformat(), "events": json.loads(r.summary_json)} for r in rows]

@router.post("/run")
def run_detection(line_id: int, stop_name: str | None = None, db: Session = Depends(get_db)):
    line = db.get(Line, line_id)
    if not line: raise HTTPException(404, "线路不存在")
    trips = db.scalars(select(Trip).where(Trip.line_id == line_id)).all()
    trip_ids = [t.id for t in trips]
    trip_no_map = {t.id: t.trip_no for t in trips}
    holds = _hold_map(db, trip_ids, trip_no_map)
    arrivals = db.scalars(select(Arrival).where(Arrival.trip_id.in_(trip_ids))).all()
    payload = [{"stop_name": a.stop_name, "trip_no": trip_no_map[a.trip_id], "actual_arrive": a.actual_arrive}
               for a in arrivals if stop_name is None or a.stop_name == stop_name]
    payload = apply_holds(payload, holds)
    events = detect_bunching(payload, line.planned_headway_min, line.bunch_threshold, line.large_threshold)
    data = events_to_dicts(events)
    report = BunchReport(line_id=line_id, stop_name=stop_name or "*", created_at=datetime.utcnow(),
                         summary_json=json.dumps(data, ensure_ascii=False))
    db.add(report); db.commit(); db.refresh(report)
    return {"id": report.id, "events": data}

@router.get("/suggestions")
def suggestions(line_id: int, db: Session = Depends(get_db)):
    result = run_detection(line_id=line_id, stop_name=None, db=db)
    return {"line_id": line_id, "suggestions": [e for e in result["events"] if e["status"] != "normal"]}

@router.get("/timeline")
def timeline(line_id: int, stop_name: str = "市民中心", db: Session = Depends(get_db)):
    trips = db.scalars(select(Trip).where(Trip.line_id == line_id)).all()
    trip_ids = [t.id for t in trips]
    trip_no_map = {t.id: t.trip_no for t in trips}
    holds = _hold_map(db, trip_ids, trip_no_map)
    arrivals = db.scalars(select(Arrival).where(Arrival.trip_id.in_(trip_ids), Arrival.stop_name == stop_name)).all()
    payload = apply_holds(
        [{"stop_name": a.stop_name, "trip_no": trip_no_map[a.trip_id], "actual_arrive": a.actual_arrive}
         for a in arrivals], holds)
    payload = sorted(payload, key=lambda a: a["actual_arrive"])
    if not payload: return {"stop_name": stop_name, "marks": []}
    t0 = payload[0]["actual_arrive"]
    span = max((payload[-1]["actual_arrive"] - t0).total_seconds(), 1)
    marks = [{"trip_no": a["trip_no"], "actual_arrive": a["actual_arrive"].isoformat(),
              "hold_min": holds.get((a["trip_no"], stop_name)) or 0,
              "pct": round((a["actual_arrive"] - t0).total_seconds() / span * 100, 2)} for a in payload]
    return {"stop_name": stop_name, "marks": marks}
