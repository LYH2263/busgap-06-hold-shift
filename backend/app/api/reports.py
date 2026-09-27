import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Arrival, BunchReport, Hold, Line, Trip
from app.services.bunch_engine import detect_bunching, events_to_dicts
from app.services.holds import build_hold_index, effective_arrive
router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("")
def list_reports(db: Session = Depends(get_db)):
    rows = db.scalars(select(BunchReport).order_by(BunchReport.id.desc())).all()
    return [{"id": r.id, "line_id": r.line_id, "stop_name": r.stop_name,
             "created_at": r.created_at.isoformat(), "events": json.loads(r.summary_json)} for r in rows]

def _line_payload(db: Session, line_id: int, stop_name: str | None):
    trips = db.scalars(select(Trip).where(Trip.line_id == line_id)).all()
    trip_ids = [t.id for t in trips]
    trip_no_map = {t.id: t.trip_no for t in trips}
    arrivals = db.scalars(select(Arrival).where(Arrival.trip_id.in_(trip_ids))).all()
    holds = db.scalars(select(Hold).where(Hold.trip_id.in_(trip_ids))).all()
    hold_index = build_hold_index(arrivals, holds)
    payload = [{"stop_name": a.stop_name, "trip_no": trip_no_map[a.trip_id],
                "actual_arrive": effective_arrive(a, hold_index)}
               for a in arrivals if stop_name is None or a.stop_name == stop_name]
    return trips, arrivals, holds, hold_index, payload

@router.post("/run")
def run_detection(line_id: int, stop_name: str | None = None, db: Session = Depends(get_db)):
    line = db.get(Line, line_id)
    if not line: raise HTTPException(404, "线路不存在")
    _, _, _, _, payload = _line_payload(db, line_id, stop_name)
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
    trips, arrivals, holds, hold_index, _ = _line_payload(db, line_id, stop_name)
    trip_no_map = {t.id: t.trip_no for t in trips}
    holds_by_trip = {h.trip_id: h for h in holds if (h.hold_min or 0) > 0}
    rows = [{"trip_no": trip_no_map[a.trip_id],
             "actual_arrive": effective_arrive(a, hold_index),
             "held": holds_by_trip.get(a.trip_id) is not None
                     and a.stop_seq >= hold_index.get(a.trip_id, (-1, 0))[0],
             "hold_min": (holds_by_trip[a.trip_id].hold_min
                          if holds_by_trip.get(a.trip_id) is not None
                          and a.stop_seq >= hold_index.get(a.trip_id, (-1, 0))[0] else 0)}
            for a in arrivals if a.stop_name == stop_name]
    rows = sorted(rows, key=lambda x: x["actual_arrive"])
    if not rows: return {"stop_name": stop_name, "marks": []}
    t0 = rows[0]["actual_arrive"]
    span = max((rows[-1]["actual_arrive"] - t0).total_seconds(), 1)
    marks = [{"trip_no": r["trip_no"], "actual_arrive": r["actual_arrive"].isoformat(),
              "pct": round((r["actual_arrive"] - t0).total_seconds() / span * 100, 2),
              "held": r["held"], "hold_min": r["hold_min"]} for r in rows]
    return {"stop_name": stop_name, "marks": marks}
