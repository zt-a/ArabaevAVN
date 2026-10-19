import base64
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger

from db.database import SessionLocal
from db.models import Group, Schedule, User, Grade, UserNotification, SyncState
from parsers.common import AuthError
from parsers.schedule import (
    fetch_schedule_for_group,
    extract_periods,
)
from parsers.auth import login as lms_login
from parsers.transcript import make_hash
from parsers.notifications import get_notifications
from parsers.userinfo import get_userinfo
from parsers.card import get_study_card, parse_grades

RETRY_AFTER_HOURS = 2
SYNC_KEY = "last_full_sync"
FAIL_KEY = "avn_fail_count"
TOKEN_REFRESH_MARGIN = 300  # секунд до истечения, когда обновляем токен


# ----------------------------- helpers -----------------------------

def _get_state(s, key: str) -> Optional[str]:
    row = s.query(SyncState).filter(SyncState.key == key).first()
    return row.value if row else None


def _set_state(s, key: str, value: str):
    row = s.query(SyncState).filter(SyncState.key == key).first()
    if row:
        row.value = value
    else:
        s.add(SyncState(key=key, value=value))


def token_is_expired(token: Optional[str]) -> bool:
    """Проверяет JWT exp (без проверки подписи). Истёкшим считаем и пустой токен."""
    if not token:
        return True
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = int(data.get("exp", 0))
        return exp < time.time() + TOKEN_REFRESH_MARGIN
    except Exception:
        return True


async def _refresh_token(user_id: int) -> Optional[str]:
    with SessionLocal() as s:
        u = s.query(User).filter(User.id == user_id).first()
        if not u:
            return None
        login, password, tg_id = u.login, u.password, u.tg_id
    result = await lms_login(login, password)
    if not result.get("success"):
        logger.warning(f"Login failed for user {tg_id}")
        return None
    token = result["token"]
    with SessionLocal() as s:
        u = s.query(User).filter(User.id == user_id).first()
        if u:
            u.token = token
            s.commit()
    return token


async def _ensure_token(user_id: int, token: Optional[str]) -> Optional[str]:
    if token_is_expired(token):
        return await _refresh_token(user_id)
    return token


# ----------------------------- schedule -----------------------------

def sync_group_schedule(group_name: str) -> bool:
    """
    Синхронизирует расписание одной группы, используя ранее сохранённые
    параметры отчёта (один запрос к AVN на группу, не на студента).
    """
    with SessionLocal() as s:
        group = s.query(Group).filter(Group.name == group_name).first()
        if not group or not group.avn_group_id or not group.avn_faculty_id or not group.periods_json:
            logger.info(f"Group {group_name}: no AVN params yet, skip")
            return False
        group_id = group.id
        avn_group_id = group.avn_group_id
        avn_faculty_id = group.avn_faculty_id
        try:
            periods = json.loads(group.periods_json)
        except Exception:
            periods = []

    if not periods:
        return False

    logger.info(f"Syncing schedule for group {group_name}...")
    lessons, period = fetch_schedule_for_group(avn_group_id, avn_faculty_id, periods)
    if not lessons:
        logger.warning(f"No lessons fetched for {group_name}")
        return False

    with SessionLocal() as s:
        group = s.query(Group).filter(Group.id == group_id).first()
        if not group:
            return False
        if period:
            group.year = period.get("year", group.year)
            group.semester = period.get("semester", group.semester)
        group.fetched_at = datetime.now()
        s.query(Schedule).filter(Schedule.group_id == group.id).delete()
        for l in lessons:
            s.add(Schedule(
                group_id=group.id,
                day_index=l["day_index"],
                day=l["day"],
                time_start=l["time_start"],
                time_end=l["time_end"],
                discipline=l["discipline"],
                teacher=l["teacher"],
                auditorium=l["auditorium"],
                building=l["building"],
                lesson_type=l["lesson_type"],
                weeks=l["weeks"],
                raw=l["raw"],
            ))
        s.commit()
        logger.info(f"Group {group_name}: {len(lessons)} lessons saved")
    return True


def sync_all_groups(force: bool = False) -> Dict:
    """
    Синхронизирует расписание всех групп, у которых есть студенты.
    Если AVN недоступен — повтор через RETRY_AFTER_HOURS часов.
    """
    with SessionLocal() as s:
        if not force:
            last = _get_state(s, SYNC_KEY)
            if last:
                try:
                    if datetime.now() - datetime.fromisoformat(last) < timedelta(hours=1):
                        return {"skipped": True, "reason": "already synced recently"}
                except Exception:
                    pass

        groups = (
            s.query(Group.name)
            .join(User, User.group_id == Group.id)
            .filter(User.is_active == True)
            .distinct()
            .all()
        )
        group_names = [g[0] for g in groups]

    results = {"ok": [], "failed": [], "no_params": []}
    for gname in group_names:
        try:
            ok = sync_group_schedule(gname)
            (results["ok"] if ok else results["no_params"]).append(gname)
        except Exception as e:
            logger.error(f"Error syncing group {gname}: {e}")
            results["failed"].append(gname)

    if results["failed"]:
        with SessionLocal() as s:
            fail_count = int(_get_state(s, FAIL_KEY) or "0") + 1
            _set_state(s, FAIL_KEY, str(fail_count))
            _set_state(s, "next_retry_at", (datetime.now() + timedelta(hours=RETRY_AFTER_HOURS)).isoformat())
        logger.warning(f"AVN issues. Failed groups: {results['failed']}")
    else:
        with SessionLocal() as s:
            _set_state(s, FAIL_KEY, "0")
            _set_state(s, SYNC_KEY, datetime.now().isoformat())

    return results


# ----------------------------- user data -----------------------------

async def _call(user_id: int, token: str, func, *args, **kwargs):
    """Вызывает парсер; при 401 один раз обновляет токен и повторяет."""
    try:
        return token, await func(token, *args, **kwargs)
    except AuthError:
        new_token = await _refresh_token(user_id)
        if not new_token:
            raise
        return new_token, await func(new_token, *args, **kwargs)


async def sync_user_data(user_id: int) -> bool:
    """
    Синхронизирует личные данные студента (профиль, оценки, уведомления)
    и обновляет параметры расписания его группы.
    """
    with SessionLocal() as s:
        user = s.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            return False
        token = user.token

    token = await _ensure_token(user_id, token)
    if not token:
        return False

    try:
        # уведомления из ЛК
        token, notifs = await _call(user_id, token, get_notifications)
        _store_notifications(user_id, notifs)

        # профиль + оценки + параметры расписания
        token, userinfo = await _call(user_id, token, get_userinfo)
        token, card = await _call(user_id, token, get_study_card)
        _store_grades(user_id, parse_grades(card))
        _store_profile(user_id, userinfo, card)
    except AuthError:
        logger.warning(f"Sync auth failed for user {user_id}")
        return False
    except Exception as e:
        logger.error(f"sync_user_data error for {user_id}: {e}")
        return False

    with SessionLocal() as s:
        u = s.query(User).filter(User.id == user_id).first()
        if u:
            u.last_sync_at = datetime.now()
            gname = u.group.name if u.group else None
            s.commit()
    if gname:
        try:
            import asyncio
            await asyncio.to_thread(sync_group_schedule, gname)
        except Exception as e:
            logger.error(f"Group schedule sync failed for {gname}: {e}")
    return True


def _store_grades(user_id: int, grades):
    if not grades:
        return
    with SessionLocal() as s:
        existing = {h[0] for h in s.query(Grade.hash_key).filter(Grade.user_id == user_id).all()}
        for item in grades:
            if not isinstance(item, dict):
                continue
            h = make_hash(item)
            if h in existing:
                continue
            s.add(Grade(
                user_id=user_id,
                semester=str(item.get("semester", "")),
                year=str(item.get("year", "")),
                discipline=str(item.get("discipline", "")),
                control_type=str(item.get("control_type", "")),
                ball=str(item.get("ball", "")),
                grade=str(item.get("grade", "")),
                teacher=str(item.get("teacher", "")),
                date=str(item.get("date", "")),
                credits=str(item.get("credits", "")),
                hash_key=h,
            ))
            existing.add(h)
        s.commit()


def _store_notifications(user_id: int, notifs):
    if not notifs:
        return
    with SessionLocal() as s:
        existing = {n[0] for n in s.query(UserNotification.content_hash).filter(UserNotification.user_id == user_id).all()}
        for n in notifs:
            if not isinstance(n, dict):
                continue
            content = json.dumps(n, sort_keys=True, ensure_ascii=False)
            ch = hashlib.sha256(content.encode()).hexdigest()
            if ch not in existing:
                s.add(UserNotification(user_id=user_id, content_hash=ch, content=content))
                existing.add(ch)
        s.commit()


def _upsert_group(s, name: str, faculty: str = "") -> Group:
    g = s.query(Group).filter(Group.name == name).first()
    if not g:
        g = Group(name=name, faculty=faculty or "ИНИТ")
        s.add(g)
        s.flush()
    return g


def _store_profile(user_id: int, userinfo: Dict, card: List[Dict]):
    userinfo = userinfo or {}
    card = card or []

    group_name = userinfo.get("doljnost", "") or ""
    faculty = userinfo.get("name_otdel", "") or ""
    avn_group_id = userinfo.get("id_group")
    avn_faculty_id = userinfo.get("id_faculty")
    periods = extract_periods(card)

    fio = ""
    group_from_card = ""
    for row in card:
        if isinstance(row, dict):
            fio = row.get("s_fio", "") or fio
            group_from_card = row.get("p20", "") or group_from_card
            if fio and group_from_card:
                break
    if group_from_card:
        group_name = group_from_card

    with SessionLocal() as s:
        u = s.query(User).filter(User.id == user_id).first()
        if not u:
            return
        if faculty:
            u.faculty = faculty
            u.speciality = faculty
        if fio:
            u.full_name = fio
        if group_name:
            g = _upsert_group(s, group_name, u.faculty or "ИНИТ")
            if avn_group_id:
                g.avn_group_id = int(avn_group_id)
            if avn_faculty_id:
                g.avn_faculty_id = int(avn_faculty_id)
            if periods:
                g.periods_json = json.dumps(periods, ensure_ascii=False)
                g.year = periods[0].get("year", g.year)
                g.semester = periods[0].get("semester", g.semester)
            u.group_id = g.id
        s.commit()


# ----------------------------- queries -----------------------------

def get_group_schedule_today(group_id: int) -> List[Dict]:
    today = datetime.now().weekday()
    with SessionLocal() as s:
        rows = (
            s.query(Schedule)
            .filter(Schedule.group_id == group_id, Schedule.day_index == today)
            .order_by(Schedule.time_start)
            .all()
        )
        return [_row_to_dict(r) for r in rows]


def get_group_schedule_tomorrow(group_id: int) -> List[Dict]:
    tomorrow = (datetime.now() + timedelta(days=1)).weekday()
    with SessionLocal() as s:
        rows = (
            s.query(Schedule)
            .filter(Schedule.group_id == group_id, Schedule.day_index == tomorrow)
            .order_by(Schedule.time_start)
            .all()
        )
        return [_row_to_dict(r) for r in rows]


def get_group_schedule_week(group_id: int) -> Dict[str, List[Dict]]:
    with SessionLocal() as s:
        rows = (
            s.query(Schedule)
            .filter(Schedule.group_id == group_id)
            .order_by(Schedule.day_index, Schedule.time_start)
            .all()
        )
        res: Dict[str, List[Dict]] = {}
        for r in rows:
            res.setdefault(r.day, []).append(_row_to_dict(r))
        return res


def _row_to_dict(r: Schedule) -> Dict:
    return {
        "day": r.day,
        "day_index": r.day_index,
        "time_start": r.time_start,
        "time_end": r.time_end,
        "discipline": r.discipline,
        "teacher": r.teacher,
        "auditorium": r.auditorium,
        "building": r.building,
        "lesson_type": r.lesson_type,
        "weeks": r.weeks,
    }
