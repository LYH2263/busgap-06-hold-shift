from datetime import datetime, timedelta
from app.services.bunch_engine import apply_holds, classify_gap, detect_bunching

def test_classify_bunching():
    assert classify_gap(2.0, 8.0, 3.0, 15.0)[0] == "bunching"

def test_classify_large():
    assert classify_gap(16.0, 8.0, 3.0, 15.0)[0] == "large_gap"

def test_classify_normal():
    assert classify_gap(8.0, 8.0, 3.0, 15.0)[0] == "normal"

def test_detect_bunching_events():
    base = datetime(2026, 1, 1, 8, 0)
    arrivals = [
        {"stop_name": "A", "trip_no": "T1", "actual_arrive": base},
        {"stop_name": "A", "trip_no": "T2", "actual_arrive": base + timedelta(minutes=2)},
        {"stop_name": "A", "trip_no": "T3", "actual_arrive": base + timedelta(minutes=20)},
    ]
    events = detect_bunching(arrivals, 8.0, 3.0, 15.0)
    assert len(events) == 2
    assert events[0].status == "bunching"
    assert events[1].status == "large_gap"

def test_apply_holds_shifts_arrival():
    base = datetime(2026, 1, 1, 8, 0)
    arrivals = [
        {"stop_name": "A", "trip_no": "T1", "actual_arrive": base},
        {"stop_name": "A", "trip_no": "T2", "actual_arrive": base + timedelta(minutes=8)},
    ]
    out = apply_holds(arrivals, {("T2", "A"): 5})
    assert out[0]["actual_arrive"] == base
    assert out[1]["actual_arrive"] == base + timedelta(minutes=13)
    # 不修改传入的原始记录
    assert arrivals[1]["actual_arrive"] == base + timedelta(minutes=8)

def test_apply_holds_zero_or_missing_unchanged():
    base = datetime(2026, 1, 1, 8, 0)
    arrivals = [
        {"stop_name": "A", "trip_no": "T1", "actual_arrive": base},
        {"stop_name": "A", "trip_no": "T2", "actual_arrive": base + timedelta(minutes=8)},
    ]
    out = apply_holds(arrivals, {("T2", "A"): 0, ("T9", "A"): 7})
    assert [a["actual_arrive"] for a in out] == [a["actual_arrive"] for a in arrivals]

def test_hold_changes_following_gap():
    # T2 扣 6 分钟:相对 T1 间隔变大,T3 相对 T2 间隔被压成串车
    base = datetime(2026, 1, 1, 8, 0)
    arrivals = [
        {"stop_name": "A", "trip_no": "T1", "actual_arrive": base},
        {"stop_name": "A", "trip_no": "T2", "actual_arrive": base + timedelta(minutes=8)},
        {"stop_name": "A", "trip_no": "T3", "actual_arrive": base + timedelta(minutes=16)},
    ]
    before = detect_bunching(arrivals, 8.0, 3.0, 15.0)
    assert all(e.status == "normal" for e in before)
    after = detect_bunching(apply_holds(arrivals, {("T2", "A"): 6}), 8.0, 3.0, 15.0)
    assert after[0].gap_min == 14.0 and after[0].status == "normal"
    assert after[1].gap_min == 2.0 and after[1].status == "bunching"
    assert after[1].earlier_trip == "T2" and after[1].later_trip == "T3"
