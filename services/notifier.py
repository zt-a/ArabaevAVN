from datetime import datetime

from aiogram import Bot
from loguru import logger

from db.database import SessionLocal
from db.models import User, Group, NotificationLog
from config.settings import settings
from services.sync import get_group_schedule_today

NOTIFY_BEFORE_MINUTES = settings.NOTIFY_BEFORE_MINUTES


def _parse_time(t: str) -> datetime:
    h, m = map(int, t.split(":"))
    now = datetime.now()
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def _dedup_key(notif_type: str, lesson: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{today}|{notif_type}|{lesson['discipline']}|{lesson['day']}|{lesson['time_start']}"


def _check_sent(user_id: int, key: str) -> bool:
    """Проверяем, не отправляли ли уже такое уведомление сегодня."""
    with SessionLocal() as s:
        exists = (
            s.query(NotificationLog)
            .filter(
                NotificationLog.user_id == user_id,
                NotificationLog.content.like(f"{key}%"),
            )
            .first()
        )
        return exists is not None


async def send_to_user(bot: Bot, tg_id: int, text: str, notif_type: str, user_id: int, dedup_key: str):
    try:
        await bot.send_message(tg_id, text, parse_mode="HTML")
        with SessionLocal() as s:
            s.add(NotificationLog(
                user_id=user_id,
                notif_type=notif_type,
                content=f"{dedup_key}\n{text}",
            ))
            s.commit()
        return True
    except Exception as e:
        logger.error(f"Send error to {tg_id}: {e}")
        return False


def _lesson_text(lesson: dict, gname: str) -> str:
    return (
        f"📚 {lesson['discipline']} ({lesson['lesson_type']})\n"
        f"🕐 {lesson['time_start']} - {lesson['time_end']}\n"
        f"📍 {lesson['auditorium']} | {lesson['building']}\n"
        f"👨‍🏫 {lesson['teacher']}\n"
        f"👥 Группа: {gname}"
    )


async def check_and_send_lesson_notifications(bot: Bot):
    """
    Проверяет расписание всех групп и шлёт уведомления:
    - за 10/5 минут до пары
    - когда пара началась
    - когда пара закончилась
    - когда перемена закончилась (напоминание идти к аудитории)
    """
    now = datetime.now()

    with SessionLocal() as s:
        users = (
            s.query(User.id, User.tg_id, User.group_id, Group.name)
            .join(Group, User.group_id == Group.id)
            .filter(User.is_active == True)
            .all()
        )
        group_ids = set(u.group_id for u in users if u.group_id)

    for gid in group_ids:
        lessons = get_group_schedule_today(gid)
        if not lessons:
            continue
        group_users = [u for u in users if u.group_id == gid]

        for lesson in lessons:
            t_start = _parse_time(lesson["time_start"])
            t_end = _parse_time(lesson["time_end"])
            diff_start = (t_start - now).total_seconds() / 60
            diff_end = (t_end - now).total_seconds() / 60
            next_lesson = next(
                (l for l in lessons if l["time_start"] > lesson["time_end"]), None
            )

            for user_id, tg_id, _, gname in group_users:
                # Уведомления до начала (окно ~1 мин, дедуп защищает от дублей)
                for notify_min in NOTIFY_BEFORE_MINUTES:
                    if notify_min - 0.2 <= diff_start < notify_min + 1:
                        key = _dedup_key(f"before_{notify_min}", lesson)
                        if _check_sent(user_id, key):
                            continue
                        text = f"⏰ <b>Пара через {notify_min} мин!</b>\n" + _lesson_text(lesson, gname)
                        await send_to_user(bot, tg_id, text, f"before_{notify_min}", user_id, key)

                # Начало пары
                if 0 <= diff_start < 1:
                    key = _dedup_key("start", lesson)
                    if not _check_sent(user_id, key):
                        text = f"🔔 <b>Пара началась!</b>\n" + _lesson_text(lesson, gname)
                        await send_to_user(bot, tg_id, text, "start", user_id, key)

                # Конец пары
                if 0 <= diff_end < 1:
                    key = _dedup_key("end", lesson)
                    if not _check_sent(user_id, key):
                        if next_lesson:
                            text = (
                                f"✅ <b>Пара закончилась</b> ({lesson['discipline']}).\n"
                                f"🔜 Следующая: {next_lesson['discipline']} в {next_lesson['time_start']}\n"
                                f"📍 {next_lesson['auditorium']} | {next_lesson['building']}\n"
                                f"👨‍🏫 {next_lesson['teacher']}"
                            )
                        else:
                            text = f"✅ <b>Пара закончилась</b> ({lesson['discipline']}). На сегодня всё!"
                        await send_to_user(bot, tg_id, text, "end", user_id, key)

                # Перемена заканчивается - напоминание идти к аудитории следующей
                if next_lesson:
                    next_start = _parse_time(next_lesson["time_start"])
                    diff_next = (next_start - now).total_seconds() / 60
                    if 0 < diff_next <= 5:
                        key = _dedup_key("break_end", next_lesson)
                        if not _check_sent(user_id, key):
                            text = (
                                f"🚶 <b>Перемена заканчивается!</b>\n"
                                f"🔜 Идите к аудитории: {next_lesson['discipline']}\n"
                                f"🕐 Начало в {next_lesson['time_start']}\n"
                                f"📍 {next_lesson['auditorium']} | {next_lesson['building']}\n"
                                f"👨‍🏫 {next_lesson['teacher']}"
                            )
                            await send_to_user(bot, tg_id, text, "break_end", user_id, key)
