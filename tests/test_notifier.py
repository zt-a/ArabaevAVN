from datetime import datetime

from db.database import SessionLocal
from db.models import NotificationLog
from services.notifier import _parse_time, _dedup_key, _check_sent


def test_parse_time_keeps_today_date():
    t = _parse_time("08:30")
    now = datetime.now()
    assert (t.hour, t.minute, t.second) == (8, 30, 0)
    assert t.date() == now.date()


def test_dedup_key_stable_for_same_lesson():
    lesson = {"discipline": "Физика", "day": "Пн", "time_start": "08:00"}
    k1 = _dedup_key("before_10", lesson)
    k2 = _dedup_key("before_10", lesson)
    assert k1 == k2
    assert k1.endswith("before_10|Физика|Пн|08:00")


def test_dedup_key_differs_by_type():
    lesson = {"discipline": "Физика", "day": "Пн", "time_start": "08:00"}
    assert _dedup_key("before_10", lesson) != _dedup_key("start", lesson)


def test_check_sent_roundtrip():
    user_id = 987654
    key = "2026-10-19|start|Физика|Пн|08:00"
    assert _check_sent(user_id, key) is False
    with SessionLocal() as s:
        s.add(NotificationLog(user_id=user_id, notif_type="start", content=f"{key}\ntext"))
        s.commit()
    assert _check_sent(user_id, key) is True
    # другой ключ не совпадает
    assert _check_sent(user_id, "2026-10-19|end|Физика|Пн|08:00") is False
