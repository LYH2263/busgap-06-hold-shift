from datetime import datetime, timedelta
from app.services.bunch_engine import classify_gap, detect_bunching

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

def test_detect_with_held_trip():
    """T2 在 A 站扣车 4 分钟：与前车间隔变大，与后车间隔变小。"""
    base = datetime(2026, 1, 1, 8, 0)
    arrivals = [
        {"stop_name": "A", "trip_no": "T1", "actual_arrive": base + timedelta(minutes=8)},
        {"stop_name": "A", "trip_no": "T2", "actual_arrive": base + timedelta(minutes=20)},  # 原始 8:16 + 扣车 4
        {"stop_name": "A", "trip_no": "T3", "actual_arrive": base + timedelta(minutes=24)},
    ]
    events = detect_bunching(arrivals, 8.0, 5.0, 15.0)
    by_pair = {e.earlier_trip + e.later_trip: e for e in events}
    assert by_pair["T1T2"].gap_min == 12.0
    assert by_pair["T2T3"].gap_min == 4.0
    assert by_pair["T2T3"].status == "bunching"
