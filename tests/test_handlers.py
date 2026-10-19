from db.database import SessionLocal
from db.models import User, Group
from bot.handlers import _extract_profile, _fmt_lessons, _get_user


def test_extract_profile_prefers_card_group_and_fio():
    userinfo = {"doljnost": "ПИН-1-24", "name_otdel": "ИНИТ"}
    card = [{"s_fio": "Иванов Иван Иванович", "p20": "ПИН-1-24"}]
    fio, group, faculty = _extract_profile(userinfo, card)
    assert fio == "Иванов Иван Иванович"
    assert group == "ПИН-1-24"
    assert faculty == "ИНИТ"


def test_extract_profile_without_card():
    fio, group, faculty = _extract_profile({"doljnost": "ПИН-2-23"}, [])
    assert fio == ""
    assert group == "ПИН-2-23"


def test_fmt_lessons_empty():
    assert "Свободный день" in _fmt_lessons([])


def test_fmt_lessons_renders_fields():
    lessons = [{
        "time_start": "08:00", "time_end": "09:20", "discipline": "Физика",
        "lesson_type": "Лекция", "teacher": "Ногаев М.А.", "auditorium": "101", "building": "Корпус №3",
    }]
    text = _fmt_lessons(lessons)
    assert "Физика" in text and "Ногаев М.А." in text and "101" in text


def test_get_user_returns_ctx_with_loaded_group():
    tg_id = 555000111
    with SessionLocal() as s:
        g = Group(name="CTX-GRP-1")
        s.add(g)
        s.flush()
        s.add(User(tg_id=tg_id, login="ctx", password="p", is_active=True, group_id=g.id, full_name="Тест Тестович"))
        s.commit()
    ctx = _get_user(tg_id)
    assert ctx is not None
    assert ctx.group_name == "CTX-GRP-1"
    assert ctx.full_name == "Тест Тестович"


def test_get_user_missing_returns_none():
    assert _get_user(999999999) is None
