import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from loguru import logger

from config.settings import settings
from db.database import init_db, SessionLocal
from db.models import User
from bot.handlers import router
from services.notifier import check_and_send_lesson_notifications
from services.sync import sync_all_groups, sync_user_data

logger.remove()
logger.add(sys.stderr, level=settings.LOG_LEVEL)
logger.add("bot.log", rotation="10 MB", retention="7 days")

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

GROUP_SYNC_INTERVAL = 3600      # 1 час
USER_SYNC_INTERVAL = 3 * 3600   # 3 часа


async def set_commands():
    commands = [
        BotCommand(command="start", description="Старт/Авторизация"),
        BotCommand(command="profile", description="Профиль студента"),
        BotCommand(command="schedule", description="Расписание"),
        BotCommand(command="grades", description="Успеваемость"),
        BotCommand(command="notifications", description="Уведомления"),
        BotCommand(command="logout", description="Сменить аккаунт/Выйти"),
    ]
    await bot.set_my_commands(commands)


async def schedule_notifier():
    while True:
        try:
            await check_and_send_lesson_notifications(bot)
        except Exception as e:
            logger.error(f"Notifier error: {e}")
        await asyncio.sleep(30)


async def schedule_group_sync():
    await asyncio.sleep(10)
    while True:
        try:
            res = await asyncio.to_thread(sync_all_groups)
            logger.info(f"Group sync: {res}")
        except Exception as e:
            logger.error(f"Group sync error: {e}")
        await asyncio.sleep(GROUP_SYNC_INTERVAL)


async def schedule_user_sync():
    await asyncio.sleep(30)
    while True:
        try:
            with SessionLocal() as s:
                user_ids = [u.id for u in s.query(User.id).filter(User.is_active == True).all()]
            for uid in user_ids:
                try:
                    await sync_user_data(uid)
                except Exception as e:
                    logger.error(f"User sync error {uid}: {e}")
        except Exception as e:
            logger.error(f"User sync loop error: {e}")
        await asyncio.sleep(USER_SYNC_INTERVAL)


async def main():
    init_db()
    await set_commands()
    asyncio.create_task(schedule_notifier())
    asyncio.create_task(schedule_group_sync())
    asyncio.create_task(schedule_user_sync())
    logger.info("AVN bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
