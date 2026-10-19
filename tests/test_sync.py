import base64
import json
import time

from db.database import SessionLocal
from db.models import User, Grade, UserNotification, Group
from services.sync import (
    token_is_expired,
    _store_grades,
    _store_notifications,
    _store_profile,
    _upsert_group,
    sync_group_schedule,
)


def _make_jwt(exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"header.{payload}.sig"


def test_token_is_expired_none():
    assert token_is_expired(None) is True
    assert token_is_expired("") is True


def test_token_is_expired_future():
    assert token_is_expired(_make_jwt(int(time.time()) + 3600)) is False


def test_token_is_expired_past():
    assert token_is_expired(_make_jwt(int(time.time()) - 10)) is True


def test_token_is_expired_within_margin():
    assert token_is_expired(_make_jwt(int(time.time()) + 60)) is True


def test_token_is_expired_garbage():
    assert token_is_expired("not-a-jwt") is True


def _mk_user(login: str) -> int:
    with SessionLocal() as s:
        u = User(tg_id=abs(hash(login)) % 10_000_000, login=login, password="p", is_active=True)
        s.add(u)
        s.commit()
        return u.id


def test_store_grades_dedup():
    uid = _mk_user("grades_test")
    rows = [{"discipline": "Физика", "ball": "80", "grade": "хор", "semester": "Осенний"}]
    _store_grades(uid, rows)
    _store_grades(uid, rows)  # повтор не должен дублировать
    with SessionLocal() as s:
        assert s.query(Grade).filter(Grade.user_id == uid).count() == 1


def test_store_notifications_dedup():
    uid = _mk_user("notif_test")
    rows = [{"title": "Привет"}]
    _store_notifications(uid, rows)
    _store_notifications(uid, rows)
    with SessionLocal() as s:
        assert s.query(UserNotification).filter(UserNotification.user_id == uid).count() == 1


def test_store_profile_sets_group_and_params():
    uid = _mk_user("profile_test")
    userinfo = {"doljnost": "ПИН-1-24", "name_otdel": "ИНИТ", "id_group": 12429, "id_faculty": 60}
    card = [
        {"s_fio": "Иванов Иван Иванович", "p20": "ПИН-1-24", "id_a_year": 26, "id_w_s": 2, "id_rate": 3, "p32": "2026-27"},
    ]
    _store_profile(uid, userinfo, card)
    with SessionLocal() as s:
        u = s.query(User).filter(User.id == uid).first()
        assert u.full_name == "Иванов Иван Иванович"
        assert u.faculty == "ИНИТ"
        g = u.group
        assert g is not None
        assert g.name == "ПИН-1-24"
        assert g.avn_group_id == 12429
        assert g.avn_faculty_id == 60
        assert '"id_a_year": 26' in (g.periods_json or "")


def test_upsert_group_reuses_existing():
    with SessionLocal() as s:
        g1 = _upsert_group(s, "TEST-GRP-1", "Фак")
        g2 = _upsert_group(s, "TEST-GRP-1", "Другой")
        assert g1.id == g2.id


def test_sync_group_schedule_without_params_returns_false():
    with SessionLocal() as s:
        s.add(Group(name="NO-PARAMS-GRP"))
        s.commit()
    assert sync_group_schedule("NO-PARAMS-GRP") is False
    assert sync_group_schedule("DOES-NOT-EXIST") is False
