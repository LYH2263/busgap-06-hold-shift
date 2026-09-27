from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.models import Hold, Trip

router = APIRouter(prefix="/trips", tags=["trips"])


class HoldIn(BaseModel):
    stop_name: str = Field(min_length=1)
    hold_min: float = Field(ge=0)


def _hold_payload(trip: Trip) -> dict | None:
    if trip.hold is None or (trip.hold.hold_min or 0) <= 0:
        return None
    return {"stop_name": trip.hold.stop_name, "hold_min": trip.hold.hold_min}


@router.get("")
def list_trips(line_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Trip).options(joinedload(Trip.hold)).order_by(Trip.planned_depart)
    if line_id is not None:
        q = q.where(Trip.line_id == line_id)
    return [{"id": r.id, "line_id": r.line_id, "trip_no": r.trip_no,
             "planned_depart": r.planned_depart.isoformat(), "vehicle_no": r.vehicle_no,
             "hold": _hold_payload(r)}
            for r in db.scalars(q).unique().all()]


@router.put("/{trip_id}/hold")
def register_hold(trip_id: int, body: HoldIn, db: Session = Depends(get_db)):
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "班次不存在")
    stop_names = {a.stop_name for a in trip.arrivals}
    if body.stop_name not in stop_names:
        raise HTTPException(400, "该班次不经过此站点")
    max_hold = trip.line.max_hold_min
    if body.hold_min > max_hold:
        # 超上限拒绝：不写入、不删除，时间轴与报告保持改前
        raise HTTPException(400, f"扣车 {body.hold_min:g} 分钟超过线路允许上限 {max_hold:g} 分钟")
    hold = db.scalar(select(Hold).where(Hold.trip_id == trip_id))
    if body.hold_min == 0:
        if hold:
            db.delete(hold)
    else:
        if hold:
            hold.stop_name = body.stop_name
            hold.hold_min = body.hold_min
        else:
            hold = Hold(trip_id=trip_id, stop_name=body.stop_name, hold_min=body.hold_min)
            db.add(hold)
    db.commit()
    db.refresh(trip)
    return {"id": trip.id, "hold": _hold_payload(trip)}
