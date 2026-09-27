"""扣车（Hold）对有效到站时刻的影响。

扣车登记在某班次某站：自该站（含）起，该班所有到站时刻整体后移 hold_min 分钟。
仅用于间隔计算与时间轴展示，不回写 planned_depart，也不改原始到站记录。
"""
from __future__ import annotations
from datetime import datetime, timedelta

from app.models.models import Arrival, Hold


def build_hold_index(arrivals: list[Arrival], holds: list[Hold]) -> dict[int, tuple[int, float]]:
    """trip_id -> (扣车站 stop_seq, 扣车分钟)，扣车 0 / 未登记不收录。"""
    holds_by_trip = {h.trip_id: h for h in holds if (h.hold_min or 0) > 0}
    index: dict[int, tuple[int, float]] = {}
    for a in arrivals:
        h = holds_by_trip.get(a.trip_id)
        if h and a.stop_name == h.stop_name:
            index[a.trip_id] = (a.stop_seq, float(h.hold_min))
    return index


def effective_arrive(arrival: Arrival, hold_index: dict[int, tuple[int, float]]) -> datetime:
    h = hold_index.get(arrival.trip_id)
    if h and arrival.stop_seq >= h[0]:
        return arrival.actual_arrive + timedelta(minutes=h[1])
    return arrival.actual_arrive
