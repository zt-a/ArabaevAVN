import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from sqlalchemy.orm import joinedload

from db.database import SessionLocal
from db.models import User, Group, Grade, UserNotification
from config.settings import settings
from parsers.auth import login as lms_login
from parsers.userinfo import get_userinfo
from parsers.card import get_study_card
from services.sync import (
    sync_user_data, sync_group_schedule,
    get_group_schedule_today, get_group_schedule_tomorrow, get_group_schedule_week,
)

router = Router()


class AuthState(StatesGroup):
    waiting_login = State()
    waiting_password = State()


main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="📚 Расписание")],
        [KeyboardButton(text="💯 Оценки"), KeyboardButton(text="🔔 Уведомления")],
        [KeyboardButton(text="👤 Сменить аккаунт"), KeyboardButton(text="🚪 Выйти")],
    ],
    resize_keyboard=True,
)


admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛠 Админ панель")],
        [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="📚 Расписание")],
        [KeyboardButton(text="💯 Оценки"), KeyboardButton(text="🔔 Уведомления")],
    ],
    resize_keyboard=True,
)


@dataclass
class UserCtx:
    id: int
    tg_id: int
    login: str
    password: str
    full_name: Optional[str]
    group_id: Optional[int]
    group_name: str
    faculty: Optional[str]
    is_admin: bool
    last_sync_at: Optional[datetime]
    token: Optional[str]


def _get_user(tg_id: int) -> Optional[UserCtx]:
    """Возвращает простой объект с уже загруженной группой (без detached ORM)."""
    with SessionLocal() as s:
        u = (
            s.query(User)
            .options(joinedload(User.group))
            .filter(User.tg_id == tg_id)
            .first()
        )
        if not u:
            return None
        return UserCtx(
            id=u.id,
            tg_id=u.tg_id,
            login=u.login,
            password=u.password,
            full_name=u.full_name,
            group_id=u.group_id,
            group_name=u.group.name if u.group else "",
            faculty=u.faculty,
            is_admin=bool(u.is_admin) or (tg_id in settings.ADMIN_IDS),
            last_sync_at=u.last_sync_at,
            token=u.token,
        )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = _get_user(message.from_user.id)
    if user:
        kb = admin_kb if user.is_admin else main_kb
        await message.answer("С возвращением! Выберите действие.", reply_markup=kb)
        return
    await message.answer(
        "Привет!\n\n"
        "Для работы бота нужен логин и пароль от AVN (https://avn.arabaev.kg).\n"
        "Я сохраню их только в нашей БД (без шифрования) — это нужно для автоматического получения данных и обновления JWT.\n\n"
        "Введи логин от ЛК (например: 24\\966741):"
    )
    await state.set_state(AuthState.waiting_login)


@router.message(AuthState.waiting_login)
async def proc_login(message: Message, state: FSMContext):
    await state.update_data(login=message.text.strip())
    await message.answer("Введи пароль от ЛК:")
    await state.set_state(AuthState.waiting_password)


def _extract_profile(userinfo: dict, card) -> tuple:
    userinfo = userinfo or {}
    fio = ""
    group_name = userinfo.get("doljnost", "") or ""
    faculty = userinfo.get("name_otdel", "") or ""
    if isinstance(card, list):
        for row in card:
            if isinstance(row, dict):
                fio = row.get("s_fio", "") or fio
                group_name = row.get("p20", "") or group_name
                if fio and group_name:
                    break
    return fio, group_name, faculty


@router.message(AuthState.waiting_password)
async def proc_password(message: Message, state: FSMContext):
    data = await state.get_data()
    login = data.get("login", "")
    password = message.text.strip()
    await message.answer("Проверяю авторизацию...")

    res = await lms_login(login, password)
    if not res.get("success"):
        await message.answer("❌ Неверный логин или пароль. Попробуй ещё раз /start")
        await state.clear()
        return

    token = res["token"]
    userinfo = {}
    card = []
    try:
        userinfo = await get_userinfo(token)
        card = await get_study_card(token)
    except Exception:
        pass
    fio, group_name, faculty = _extract_profile(userinfo, card)

    with SessionLocal() as s:
        group = None
        if group_name:
            group = s.query(Group).filter(Group.name == group_name).first()
            if not group:
                group = Group(name=group_name, faculty=faculty or "ИНИТ")
                s.add(group)
                s.flush()
        user = s.query(User).filter(User.tg_id == message.from_user.id).first()
        if user:
            user.login = login
            user.password = password
            user.token = token
            user.full_name = fio or user.full_name
            user.faculty = faculty or user.faculty
            user.speciality = faculty or user.speciality
            user.group_id = group.id if group else user.group_id
            user.is_active = True
        else:
            user = User(
                tg_id=message.from_user.id,
                login=login,
                password=password,
                full_name=fio,
                group_id=group.id if group else None,
                faculty=faculty,
                speciality=faculty,
                token=token,
                is_active=True,
            )
            s.add(user)
        user.is_admin = bool(user.is_admin) or (message.from_user.id in settings.ADMIN_IDS)
        s.commit()
        user_id = user.id

    await sync_user_data(user_id)

    fresh = _get_user(message.from_user.id)
    kb = admin_kb if fresh and fresh.is_admin else main_kb
    gname = fresh.group_name if fresh and fresh.group_name else group_name
    await message.answer(
        f"✅ Авторизация успешна!\n"
        f"ФИО: {(fresh.full_name if fresh else fio) or '—'}\n"
        f"Группа: {gname or '—'}\n\n"
        f"Бот готов. Я буду присылать уведомления о парах, оценках и событиях из ЛК.",
        reply_markup=kb,
    )
    await state.clear()


@router.message(Command("profile"))
@router.message(F.text == "📊 Профиль")
async def cmd_profile(message: Message):
    user = _get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала авторизуйся: /start")
        return
    group_name = user.group_name or "—"
    await message.answer(
        f"👤 <b>Профиль студента</b>\n\n"
        f"ФИО: {user.full_name or '—'}\n"
        f"Группа: {group_name}\n"
        f"Специальность: {user.faculty or '—'}\n"
        f"Логин AVN: {user.login}\n"
        f"Последнее обновление: {user.last_sync_at.strftime('%d.%m.%Y %H:%M') if user.last_sync_at else '—'}",
        parse_mode="HTML",
    )


def _fmt_lessons(lessons) -> str:
    if not lessons:
        return "Свободный день 🎉\n"
    out = ""
    for l in lessons:
        out += (
            f"🕐 {l['time_start']}-{l['time_end']}  {l['discipline']} ({l['lesson_type']})\n"
            f"   👨‍🏫 {l['teacher'] or '—'} | 📍 {l['auditorium'] or '—'} {l['building'] or ''}\n\n"
        )
    return out


@router.message(Command("schedule"))
@router.message(F.text == "📚 Расписание")
async def cmd_schedule(message: Message):
    user = _get_user(message.from_user.id)
    if not user or not user.group_id:
        await message.answer("Сначала авторизуйся: /start")
        return
    today = get_group_schedule_today(user.group_id)
    tomorrow = get_group_schedule_tomorrow(user.group_id)
    now = datetime.now()
    tomorrow_dt = now + timedelta(days=1)
    text = f"📅 <b>Сегодня ({now.strftime('%d.%m')})</b>\n\n" + _fmt_lessons(today)
    text += f"\n📅 <b>Завтра ({tomorrow_dt.strftime('%d.%m')})</b>\n\n" + _fmt_lessons(tomorrow)
    await message.answer(text[:4000], parse_mode="HTML")


@router.message(Command("grades"))
@router.message(F.text == "💯 Оценки")
async def cmd_grades(message: Message):
    user = _get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала авторизуйся: /start")
        return
    with SessionLocal() as s:
        grades = (
            s.query(Grade)
            .filter(Grade.user_id == user.id)
            .order_by(Grade.semester, Grade.discipline)
            .all()
        )
        rows = [
            (g.year, g.semester, g.discipline, g.ball, g.grade, g.control_type)
            for g in grades
        ]
    if not rows:
        await message.answer("Пока нет оценок.")
        return
    text = "💯 <b>Твои оценки</b>\n"
    current_sem = None
    for year, sem, disc, ball, grade, ctype in rows:
        if sem != current_sem:
            current_sem = sem
            text += f"\n📚 <b>{year} — {sem}</b>\n"
        text += f"• {disc}: {ball} ({grade}) [{ctype}]\n"
    await message.answer(text[:4000], parse_mode="HTML")


@router.message(Command("notifications"))
@router.message(F.text == "🔔 Уведомления")
async def cmd_notifications(message: Message):
    user = _get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала авторизуйся: /start")
        return
    with SessionLocal() as s:
        notifs = (
            s.query(UserNotification)
            .filter(UserNotification.user_id == user.id)
            .order_by(UserNotification.id.desc())
            .limit(15)
            .all()
        )
        contents = [n.content[:200] for n in notifs]
    if not contents:
        await message.answer("Нет уведомлений из ЛК.")
        return
    text = "🔔 <b>Уведомления из ЛК</b>\n\n"
    for c in contents:
        text += f"• {c}\n\n"
    await message.answer(text[:4000], parse_mode="HTML")


@router.message(F.text == "👤 Сменить аккаунт")
async def cmd_change_acc(message: Message, state: FSMContext):
    with SessionLocal() as s:
        s.query(User).filter(User.tg_id == message.from_user.id).delete()
        s.commit()
    await state.clear()
    await message.answer(
        "Аккаунт удалён из бота.\nНажми /start чтобы авторизоваться под другим логином/паролем."
    )


@router.message(F.text == "🚪 Выйти")
async def cmd_logout(message: Message):
    with SessionLocal() as s:
        s.query(User).filter(User.tg_id == message.from_user.id).delete()
        s.commit()
    await message.answer("Вы вышли. Данные удалены из нашей БД. /start для авторизации.")


@router.message(Command("logout"))
async def cmd_logout_cmd(message: Message):
    with SessionLocal() as s:
        s.query(User).filter(User.tg_id == message.from_user.id).delete()
        s.commit()
    await message.answer("Данные удалены. /start для авторизации.")


@router.message(F.text == "🛠 Админ панель")
async def admin_panel(message: Message):
    user = _get_user(message.from_user.id)
    if not user or not user.is_admin:
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить расписание всех групп", callback_data="admin_sync_all")],
            [InlineKeyboardButton(text="🔄 Синхронизировать мою учётку", callback_data="admin_sync_me")],
            [InlineKeyboardButton(text="Статистика", callback_data="admin_stats")],
        ]
    )
    await message.answer("Админ-панель", reply_markup=kb)


@router.callback_query(F.data == "admin_sync_all")
async def cb_sync_all(call):
    await call.message.answer("Запускаю синхронизацию расписания всех групп...")
    from services.sync import sync_all_groups

    res = await asyncio.to_thread(sync_all_groups, True)
    await call.message.answer(f"Готово.\nУспешно: {res.get('ok')}\nБез параметров: {res.get('no_params')}\nОшибки: {res.get('failed')}")
    await call.answer()


@router.callback_query(F.data == "admin_sync_me")
async def cb_sync_me(call):
    user = _get_user(call.from_user.id)
    if user:
        await sync_user_data(user.id)
        await call.message.answer("Мои данные синхронизированы")
    await call.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_stats(call):
    with SessionLocal() as s:
        users = s.query(User).count()
        groups = s.query(Group).count()
    await call.message.answer(f"Статистика:\nПользователей: {users}\nГрупп: {groups}")
    await call.answer()
