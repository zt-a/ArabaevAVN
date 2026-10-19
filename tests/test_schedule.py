from datetime import datetime

from parsers.schedule import (
    _parse_lesson,
    _split_discipline_teacher,
    _parse_xml,
    extract_periods,
    is_lesson_this_week,
    lessons_for_weekday,
    next_monday,
)


def test_split_discipline_teacher():
    disc, teacher = _split_discipline_teacher("Физика Ногаев М.А.")
    assert disc == "Физика"
    assert teacher == "Ногаев М.А."


def test_split_discipline_teacher_multiword():
    disc, teacher = _split_discipline_teacher("Алгоритмический язык 1,2,3 Ачекеев  К.С.")
    assert disc == "Алгоритмический язык 1,2,3"
    assert teacher == "Ачекеев К.С."


def test_split_discipline_without_teacher():
    disc, teacher = _split_discipline_teacher("Неизвестная дисциплина")
    assert disc == "Неизвестная дисциплина"
    assert teacher == ""


def test_parse_lesson_full():
    raw = "[Пр.] Статистический анализ Алымбаев А.Т.  [нед.1-16] ауд. Вакансия Корпус №1"
    l = _parse_lesson(raw, "08:00-09:20", "08:00", "09:20", "Пн", 0)
    assert l["lesson_type"] == "Практика"
    assert l["discipline"] == "Статистический анализ"
    assert l["teacher"] == "Алымбаев А.Т."
    assert l["weeks"] == "1-16"
    assert l["auditorium"] == "Вакансия"
    assert l["building"] == "Корпус №1"
    assert l["time_start"] == "08:00"
    assert l["day_index"] == 0


def test_parse_lesson_lab_with_room():
    raw = "[Лб.] Физика Мырзабекова Ж.М.  [нед.1-16] ауд. 101 Корпус №3"
    l = _parse_lesson(raw, "09:30-10:50", "09:30", "10:50", "Вт", 1)
    assert l["lesson_type"] == "Лабораторная"
    assert l["auditorium"] == "101"
    assert l["building"] == "Корпус №3"


def test_parse_lesson_fallback_without_weeks():
    l = _parse_lesson("Что-то непонятное", "08:00-09:20", "08:00", "09:20", "Ср", 2)
    assert l["discipline"] == "Что-то непонятное"
    assert l["weeks"] == ""


def test_is_lesson_this_week_range():
    assert is_lesson_this_week("1-16", 5) is True
    assert is_lesson_this_week("1-16", 17) is False


def test_is_lesson_this_week_list():
    assert is_lesson_this_week("1,3,5", 3) is True
    assert is_lesson_this_week("1,3,5", 2) is False


def test_is_lesson_this_week_step():
    assert is_lesson_this_week("1+2", 5) is True
    assert is_lesson_this_week("1+2", 6) is False


def test_is_lesson_this_week_empty_means_always():
    assert is_lesson_this_week("", 7) is True


def test_lessons_for_weekday_sorted():
    lessons = [
        {"day_index": 0, "time_start": "12:30"},
        {"day_index": 0, "time_start": "08:00"},
        {"day_index": 1, "time_start": "09:00"},
    ]
    res = lessons_for_weekday(lessons, 0)
    assert [l["time_start"] for l in res] == ["08:00", "12:30"]


def test_extract_periods_dedup_and_sorted():
    card = [
        {"id_a_year": 24, "id_w_s": 2, "id_rate": 1, "p32": "2024-25"},
        {"id_a_year": 24, "id_w_s": 2, "id_rate": 1, "p32": "2024-25"},
        {"id_a_year": 26, "id_w_s": 2, "id_rate": 3, "p32": "2026-27"},
        {"id_a_year": 25, "id_w_s": 1, "id_rate": 2, "p32": "2025-26"},
        {"p32": "без id"},
    ]
    periods = extract_periods(card)
    assert [(p["id_a_year"], p["id_w_s"]) for p in periods] == [(26, 2), (25, 1), (24, 2)]
    assert periods[0]["semester"] == "Осенний семестр"


def test_parse_xml_realistic():
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Report xmlns="raspisanie_group">'
        '<matrix1><matrix1_Time__Collection>'
        '<matrix1_Time_ Time_="08:00-09:20">'
        '<matrix1_day_number_Collection>'
        '<matrix1_day_number Day_name="Пн">'
        '<Cell><Tablix4><Сведения_Collection>'
        '<Сведения id_faculty="[Лк.] Физика Ногаев М.А.  [нед.1-16] ауд. 101 Корпус №3" />'
        '<Сведения id_faculty="" />'
        '</Сведения_Collection></Tablix4></Cell>'
        '</matrix1_day_number>'
        '</matrix1_day_number_Collection>'
        '</matrix1_Time_>'
        '</matrix1_Time__Collection></matrix1>'
        '</Report>'
    ).encode("utf-8")
    lessons = _parse_xml(xml)
    assert len(lessons) == 1
    assert lessons[0]["discipline"] == "Физика"
    assert lessons[0]["day"] == "Пн"


def test_parse_xml_broken():
    assert _parse_xml(b"not xml at all <<<") == []


def test_next_monday_is_future_monday():
    wed = datetime(2026, 10, 14)  # среда
    nxt = next_monday(wed)
    assert nxt.weekday() == 0
    assert nxt > wed
