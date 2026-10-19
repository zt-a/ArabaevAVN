import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests
from loguru import logger

BASE = "https://avn.arabaev.kg"
REPORT_SERVER = f"{BASE}/ReportServer"
REPORT_PATH = "/VUZ/raspisanie_group"

# id_w_s: 1=Весенний, 2=Осенний, 3=Летний
SEM_NAMES = {
    1: "Весенний семестр",
    2: "Осенний семестр",
    3: "Летний семестр",
}

DAY_MAP = {
    "Пн": 0, "Вт": 1, "Ср": 2, "Чт": 3, "Пт": 4, "Сб": 5, "Вс": 6,
}
LESSON_TYPE_MAP = {
    "Лк.": "Лекция",
    "Пр.": "Практика",
    "Лб.": "Лабораторная",
}

RAW_LESSON_RE = re.compile(
    r"^\[(?P<typ>[^\]]+)\]\s*(?P<body>.+?)\s*\[нед\.(?P<weeks>[^\]]+)\]\s*ауд\.\s*(?P<aud>.*?)\s*(?P<building>Корпус\s*.*)?$",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"^(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})$")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/xml,text/xml,*/*",
}


def fetch_schedule_xml(
    id_a_year: int,
    id_w_s: int,
    id_faculty: int,
    id_rate: int,
    id_group: int,
    timeout: int = 60,
) -> List[Dict]:
    """
    Прямой экспорт отчёта SSRS в XML через URL Access.
    Параметры берутся из AVN API (user-info / study-card):
      id_a_year  - учебный год (напр. 25 = 2025-26)
      id_w_s     - семестр (1=весна, 2=осень, 3=лето)
      id_faculty - факультет
      id_rate    - курс
      id_group   - группа
    """
    url = (
        f"{REPORT_SERVER}?{REPORT_PATH}"
        f"&rs:Command=Render&rs:Format=XML"
        f"&id_a_year={id_a_year}&id_w_s={id_w_s}"
        f"&id_faculty={id_faculty}&id_rate={id_rate}&id_group={id_group}"
    )
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout)
    except Exception as e:
        logger.error(f"Schedule report request error: {e}")
        return []
    if r.status_code != 200 or len(r.content) < 400:
        logger.warning(f"Schedule report failed: {r.status_code} len={len(r.content)}")
        return []
    return _parse_xml(r.content)


def extract_periods(study_card: List[Dict]) -> List[Dict]:
    """
    Извлекает уникальные учебные периоды (год/семестр/курс) из study-card.
    Возвращает список, отсортированный от самых новых к старым.
    """
    seen: Dict[tuple, Dict] = {}
    for row in study_card or []:
        if not isinstance(row, dict):
            continue
        year_id = row.get("id_a_year")
        sem_id = row.get("id_w_s")
        rate = row.get("id_rate")
        if year_id is None or sem_id is None or rate is None:
            continue
        key = (year_id, sem_id, rate)
        if key in seen:
            continue
        seen[key] = {
            "id_a_year": int(year_id),
            "id_w_s": int(sem_id),
            "id_rate": int(rate),
            "year": row.get("p32", ""),
            "semester": SEM_NAMES.get(int(sem_id), row.get("p42", "")),
        }
    return sorted(seen.values(), key=lambda p: (p["id_a_year"], p["id_w_s"]), reverse=True)


def fetch_schedule_for_group(
    id_group: int,
    id_faculty: int,
    periods: List[Dict],
    timeout: int = 60,
) -> tuple:
    """
    Пробует периоды (от новых к старым) и возвращает первый непустой результат.
    Возвращает (lessons, period) или ([], None).
    """
    for p in periods:
        lessons = fetch_schedule_xml(
            id_a_year=p["id_a_year"],
            id_w_s=p["id_w_s"],
            id_faculty=id_faculty,
            id_rate=p["id_rate"],
            id_group=id_group,
            timeout=timeout,
        )
        if lessons:
            return lessons, p
    return [], None


def _parse_xml(xml_bytes: bytes) -> List[Dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
        return []

    lessons: List[Dict] = []
    for t in root.findall(".//{*}matrix1_Time_"):
        time_range = (t.get("Time_") or "").strip()
        tm = TIME_RE.match(time_range)
        time_start = tm.group(1) if tm else ""
        time_end = tm.group(2) if tm else ""
        for d in t.findall(".//{*}matrix1_day_number"):
            day_name = (d.get("Day_name") or "").strip()
            day_idx = DAY_MAP.get(day_name, -1)
            for s in d.findall(".//{*}Сведения"):
                raw = (s.get("id_faculty") or "").strip()
                if not raw:
                    continue
                lessons.append(_parse_lesson(raw, time_range, time_start, time_end, day_name, day_idx))
    return lessons


def _parse_lesson(raw: str, time_range: str, time_start: str, time_end: str, day_name: str, day_idx: int) -> Dict:
    m = RAW_LESSON_RE.match(raw)
    if m:
        typ = LESSON_TYPE_MAP.get(m.group("typ").strip(), m.group("typ").strip())
        body = m.group("body").strip()
        weeks = m.group("weeks").strip()
        aud = (m.group("aud") or "").strip()
        building = (m.group("building") or "").strip()
        discipline, teacher = _split_discipline_teacher(body)
    else:
        typ, weeks, aud, building = "", "", "", ""
        discipline, teacher = _split_discipline_teacher(raw)

    return {
        "day": day_name,
        "day_index": day_idx,
        "time_range": time_range,
        "time_start": time_start,
        "time_end": time_end,
        "discipline": discipline,
        "teacher": teacher,
        "lesson_type": typ,
        "auditorium": aud,
        "building": building,
        "weeks": weeks,
        "raw": raw,
    }


def _split_discipline_teacher(body: str) -> tuple:
    """
    Примеры:
      'Физика Ногаев М.А.'
      'Алгоритмический язык 1,2,3 Ачекеев  К.С.'
      'Кыргызский язык и литература Смаилова А.Т.'
    Имя преподавателя обычно в конце: Фамилия И.О.
    """
    m = re.search(r"([А-ЯЁ][а-яё\-]+(?:\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.)?)\s*$", body)
    if m:
        teacher = re.sub(r"\s+", " ", m.group(1)).strip()
        discipline = body[: m.start()].strip()
        return discipline or body, teacher
    return body, ""


def is_lesson_this_week(weeks: str, current_week: int) -> bool:
    """Проверяет, попадает ли номер недели в диапазон/список недель."""
    if not weeks:
        return True
    weeks = weeks.replace(" ", "")
    for part in weeks.split(","):
        m = re.match(r"^(\d+)-(\d+)$", part)
        if m:
            if int(m.group(1)) <= current_week <= int(m.group(2)):
                return True
            continue
        m2 = re.match(r"^(\d+)$", part)
        if m2 and int(m2.group(1)) == current_week:
            return True
        m3 = re.match(r"^(\d+)\+(\d+)$", part)  # 1+2 - через нед.
        if m3:
            start, step = int(m3.group(1)), int(m3.group(2))
            if current_week >= start and (current_week - start) % step == 0:
                return True
    return False


def next_monday(d: Optional[datetime] = None) -> datetime:
    d = d or datetime.now()
    delta = (7 - d.weekday()) % 7
    if delta == 0:
        delta = 7
    return d + timedelta(days=delta)


def lessons_for_weekday(lessons: List[Dict], weekday: int) -> List[Dict]:
    res = [l for l in lessons if l["day_index"] == weekday]
    res.sort(key=lambda l: l["time_start"])
    return res
