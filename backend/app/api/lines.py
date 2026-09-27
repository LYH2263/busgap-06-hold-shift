from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Line
router = APIRouter(prefix="/lines", tags=["lines"])

@router.get("")
def list_lines(db: Session = Depends(get_db)):
    rows = db.scalars(select(Line).order_by(Line.id)).all()
    return [{"id": r.id, "code": r.code, "name": r.name, "planned_headway_min": r.planned_headway_min,
             "bunch_threshold": r.bunch_threshold, "large_threshold": r.large_threshold,
             "max_hold_min": r.max_hold_min} for r in rows]
