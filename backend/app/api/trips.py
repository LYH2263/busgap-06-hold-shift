from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Arrival, Trip, TripHold
router = APIRouter(prefix="/trips", tags=["trips"])

class HoldIn(BaseModel):
    stop_name: str = Field(min_length=1, max_length=64)
    hold_minutes: float = Field(ge=0)

def _trip_dict(t: Trip) -> dict:
    return {"id": t.id, "line_id": t.line_id, "trip_no": t.trip_no,
            "planned_depart": t.planned_depart.isoformat(), "vehicle_no": t.vehicle_no,
            "holds": [{"stop_name": h.stop_name, "hold_minutes": h.hold_minutes} for h in t.holds]}

@router.get("")
def list_trips(line_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Trip).order_by(Trip.planned_depart)
    if line_id is not None: q = q.where(Trip.line_id == line_id)
    return [_trip_dict(t) for t in db.scalars(q).all()]

@router.put("/{trip_id}/holds")
def upsert_hold(trip_id: int, body: HoldIn, db: Session = Depends(get_db)):
    trip = db.get(Trip, trip_id)
    if not trip: raise HTTPException(404, "班次不存在")
    line = trip.line
    if body.hold_minutes > line.max_hold_min:
        raise HTTPException(400, f"扣车 {body.hold_minutes:g} 分钟超过线路允许上限 {line.max_hold_min:g} 分钟,未登记")
    stops = {a.stop_name for a in db.scalars(select(Arrival).where(Arrival.trip_id == trip_id)).all()}
    if body.stop_name not in stops:
        raise HTTPException(400, f"班次 {trip.trip_no} 在「{body.stop_name}」无到站记录,未登记")
    hold = db.scalar(select(TripHold).where(TripHold.trip_id == trip_id, TripHold.stop_name == body.stop_name))
    if hold is None:
        hold = TripHold(trip_id=trip_id, stop_name=body.stop_name, hold_minutes=body.hold_minutes)
        db.add(hold)
    else:
        hold.hold_minutes = body.hold_minutes
    db.commit(); db.refresh(trip)
    return _trip_dict(trip)
