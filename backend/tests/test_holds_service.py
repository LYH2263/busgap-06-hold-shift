from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import Arrival, Hold, Line, Trip
from app.services.holds import build_hold_index, effective_arrive


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    base = datetime(2026, 9, 17, 7, 0, 0)
    line = Line(code="B12", name="测试线", planned_headway_min=8.0,
                bunch_threshold=3.0, large_threshold=15.0, max_hold_min=5.0)
    db.add(line); db.flush()
    stops = ["起点站", "市民中心", "火车站", "终点站"]
    for trip_no, offset in [("T01", 0), ("T02", 8), ("T03", 16)]:
        trip = Trip(line_id=line.id, trip_no=trip_no,
                    planned_depart=base + timedelta(minutes=offset), vehicle_no=trip_no)
        db.add(trip); db.flush()
        for seq, stop in enumerate(stops):
            db.add(Arrival(trip_id=trip.id, stop_name=stop, stop_seq=seq,
                           actual_arrive=base + timedelta(minutes=offset + seq * 6)))
    db.commit()
    return line


def test_effective_arrive_shifts_from_hold_stop_onward():
    db = _db(); line = _seed(db)
    t02 = db.query(Trip).filter_by(trip_no="T02").one()
    db.add(Hold(trip_id=t02.id, stop_name="市民中心", hold_min=4.0)); db.commit()
    arrivals = db.query(Arrival).filter_by(trip_id=t02.id).order_by(Arrival.stop_seq).all()
    holds = db.query(Hold).all()
    idx = build_hold_index(arrivals, holds)
    base = arrivals[0].actual_arrive
    assert effective_arrive(arrivals[0], idx) == base                      # 扣车前一站不动
    assert effective_arrive(arrivals[1], idx) == base + timedelta(minutes=10)  # 扣车站 +4
    assert effective_arrive(arrivals[2], idx) == base + timedelta(minutes=16)  # 之后各站 +4


def test_zero_and_missing_hold_have_no_effect():
    db = _db(); _seed(db)
    arrivals = db.query(Arrival).all()
    assert build_hold_index(arrivals, []) == {}
    t01 = db.query(Trip).filter_by(trip_no="T01").one()
    db.add(Hold(trip_id=t01.id, stop_name="起点站", hold_min=0.0)); db.commit()
    assert build_hold_index(arrivals, db.query(Hold).all()) == {}
