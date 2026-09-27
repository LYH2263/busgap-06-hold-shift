from datetime import datetime, timedelta

from app.models.models import Arrival, Line, Trip

BASE = datetime(2026, 9, 17, 7, 0, 0)
STOPS = ["起点站", "市民中心", "火车站", "终点站"]


def seed_line(db, max_hold_min=10.0):
    line = Line(code="B12", name="城东环线", planned_headway_min=8.0,
                bunch_threshold=3.0, large_threshold=15.0, max_hold_min=max_hold_min)
    db.add(line)
    db.flush()
    trips = []
    for i, offset in enumerate([0, 8, 16]):
        trip = Trip(line_id=line.id, trip_no=f"T0{i + 1}",
                    planned_depart=BASE + timedelta(minutes=offset), vehicle_no=f"粤A100{i + 1}")
        db.add(trip)
        db.flush()
        for seq, stop in enumerate(STOPS):
            db.add(Arrival(trip_id=trip.id, stop_name=stop, stop_seq=seq,
                           actual_arrive=BASE + timedelta(minutes=offset + seq * 6)))
        trips.append(trip)
    db.commit()
    return line, trips


def events_at(client, line_id, stop):
    res = client.post(f"/api/reports/run?line_id={line_id}")
    assert res.status_code == 200
    return [e for e in res.json()["events"] if e["stop_name"] == stop]


def test_register_hold_persists(client, db_session):
    line, trips = seed_line(db_session)
    res = client.put(f"/api/trips/{trips[1].id}/holds",
                     json={"stop_name": "市民中心", "hold_minutes": 6})
    assert res.status_code == 200
    assert res.json()["holds"] == [{"stop_name": "市民中心", "hold_minutes": 6.0}]
    # 离开再进来(重新查询)仍在
    listed = client.get("/api/trips").json()
    t2 = next(t for t in listed if t["trip_no"] == "T02")
    assert t2["holds"] == [{"stop_name": "市民中心", "hold_minutes": 6.0}]


def test_hold_over_limit_rejected_and_nothing_changes(client, db_session):
    line, trips = seed_line(db_session)
    before_timeline = client.get(f"/api/reports/timeline?line_id={line.id}&stop_name=市民中心").json()
    before_events = events_at(client, line.id, "市民中心")

    res = client.put(f"/api/trips/{trips[1].id}/holds",
                     json={"stop_name": "市民中心", "hold_minutes": 11})
    assert res.status_code == 400
    assert "上限" in res.json()["detail"]

    # 未落库:班次、时间轴、报告全部保持改前
    listed = client.get("/api/trips").json()
    assert all(t["holds"] == [] for t in listed)
    after_timeline = client.get(f"/api/reports/timeline?line_id={line.id}&stop_name=市民中心").json()
    assert after_timeline["marks"] == before_timeline["marks"]
    assert events_at(client, line.id, "市民中心") == before_events


def test_hold_shifts_timeline_and_report_gaps(client, db_session):
    line, trips = seed_line(db_session)
    client.put(f"/api/trips/{trips[1].id}/holds",
               json={"stop_name": "市民中心", "hold_minutes": 6})

    # 时间轴:T02 在市民中心右移(50% → 87.5%),到站时刻为扣车后时刻
    marks = client.get(f"/api/reports/timeline?line_id={line.id}&stop_name=市民中心").json()["marks"]
    by_no = {m["trip_no"]: m for m in marks}
    assert by_no["T02"]["pct"] == 87.5
    assert by_no["T02"]["hold_min"] == 6.0
    assert by_no["T02"]["actual_arrive"] == (BASE + timedelta(minutes=8 + 6 + 6)).isoformat()
    assert by_no["T01"]["hold_min"] == 0

    # 重新检测:报告事件使用扣车后的间隔
    events = events_at(client, line.id, "市民中心")
    assert [(e["gap_min"], e["status"]) for e in events] == [(14.0, "normal"), (2.0, "bunching")]
    assert events[1]["earlier_trip"] == "T02" and events[1]["later_trip"] == "T03"


def test_hold_zero_behaves_like_unregistered(client, db_session):
    line, trips = seed_line(db_session)
    res = client.put(f"/api/trips/{trips[1].id}/holds",
                     json={"stop_name": "市民中心", "hold_minutes": 0})
    assert res.status_code == 200
    marks = client.get(f"/api/reports/timeline?line_id={line.id}&stop_name=市民中心").json()["marks"]
    assert [m["pct"] for m in marks] == [0.0, 50.0, 100.0]
    events = events_at(client, line.id, "市民中心")
    assert all(e["status"] == "normal" and e["gap_min"] == 8.0 for e in events)


def test_hold_only_affects_its_own_stop(client, db_session):
    line, trips = seed_line(db_session)
    client.put(f"/api/trips/{trips[1].id}/holds",
               json={"stop_name": "市民中心", "hold_minutes": 6})
    events = events_at(client, line.id, "火车站")
    assert all(e["status"] == "normal" and e["gap_min"] == 8.0 for e in events)


def test_hold_unknown_stop_rejected(client, db_session):
    line, trips = seed_line(db_session)
    res = client.put(f"/api/trips/{trips[1].id}/holds",
                     json={"stop_name": "不存在的站", "hold_minutes": 3})
    assert res.status_code == 400


def test_hold_unknown_trip_404(client, db_session):
    seed_line(db_session)
    res = client.put("/api/trips/9999/holds", json={"stop_name": "市民中心", "hold_minutes": 3})
    assert res.status_code == 404


def test_planned_depart_not_modified(client, db_session):
    line, trips = seed_line(db_session)
    before = {t["trip_no"]: t["planned_depart"] for t in client.get("/api/trips").json()}
    client.put(f"/api/trips/{trips[1].id}/holds",
               json={"stop_name": "市民中心", "hold_minutes": 6})
    client.post(f"/api/reports/run?line_id={line.id}")
    after = {t["trip_no"]: t["planned_depart"] for t in client.get("/api/trips").json()}
    assert after == before
    assert after["T02"] == (BASE + timedelta(minutes=8)).isoformat()


def test_lines_expose_max_hold_min(client, db_session):
    seed_line(db_session, max_hold_min=7.5)
    rows = client.get("/api/lines").json()
    assert rows[0]["max_hold_min"] == 7.5
