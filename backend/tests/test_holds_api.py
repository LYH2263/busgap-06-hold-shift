from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as mainmod
from app.database import Base, get_db
from app.main import app
from app.models.models import Arrival, Hold, Line, Trip


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    # 让 lifespan 用 SQLite，且不执行种子逻辑
    monkeypatch.setattr(mainmod, "engine", engine)
    monkeypatch.setattr(mainmod.settings, "seed_on_empty", False)
    db = TestingSession()
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

    def override_get_db():
        try:
            yield TestingSession()
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _trip_id(client, no):
    rows = client.get("/api/trips").json()
    return next(r["id"] for r in rows if r["trip_no"] == no)


def test_register_hold_persists_and_shifts_report_and_timeline(client):
    tid = _trip_id(client, "T02")
    planned_before = next(r for r in client.get("/api/trips").json() if r["id"] == tid)["planned_depart"]

    r = client.put(f"/api/trips/{tid}/hold", json={"stop_name": "市民中心", "hold_min": 4})
    assert r.status_code == 200
    assert r.json()["hold"] == {"stop_name": "市民中心", "hold_min": 4.0}

    # 离开再进来仍在；计划发车时刻字段不变
    row = next(r for r in client.get("/api/trips").json() if r["id"] == tid)
    assert row["hold"]["hold_min"] == 4.0
    assert row["planned_depart"] == planned_before

    # 时间轴：T02 右移并标记扣车
    marks = {m["trip_no"]: m for m in client.get("/api/reports/timeline?line_id=1").json()["marks"]}
    assert marks["T02"]["held"] is True
    assert marks["T02"]["hold_min"] == 4.0
    assert marks["T02"]["pct"] > marks["T01"]["pct"]

    # 重新检测：T01->T02 间隔 12，T02->T03 间隔 4（扣车后变小；阈值 3，4 仍属正常）
    events = {(e["earlier_trip"], e["later_trip"]): e
              for e in client.post("/api/reports/run?line_id=1").json()["events"]
              if e["stop_name"] == "市民中心"}
    assert events[("T01", "T02")]["gap_min"] == 12.0
    assert events[("T02", "T03")]["gap_min"] == 4.0


def test_hold_over_limit_rejected_and_state_unchanged(client):
    tid = _trip_id(client, "T02")
    before_marks = client.get("/api/reports/timeline?line_id=1").json()["marks"]

    r = client.put(f"/api/trips/{tid}/hold", json={"stop_name": "市民中心", "hold_min": 6})
    assert r.status_code == 400

    # 没有任何扣车落库；时间轴保持改前
    assert next(x for x in client.get("/api/trips").json() if x["id"] == tid)["hold"] is None
    after_marks = client.get("/api/reports/timeline?line_id=1").json()["marks"]
    assert after_marks == before_marks


def test_zero_hold_clears_registration(client):
    tid = _trip_id(client, "T02")
    assert client.put(f"/api/trips/{tid}/hold", json={"stop_name": "市民中心", "hold_min": 3}).status_code == 200
    assert client.put(f"/api/trips/{tid}/hold", json={"stop_name": "市民中心", "hold_min": 0}).status_code == 200
    assert next(x for x in client.get("/api/trips").json() if x["id"] == tid)["hold"] is None


def test_unknown_stop_rejected(client):
    tid = _trip_id(client, "T02")
    r = client.put(f"/api/trips/{tid}/hold", json={"stop_name": "不存在站", "hold_min": 1})
    assert r.status_code == 400
