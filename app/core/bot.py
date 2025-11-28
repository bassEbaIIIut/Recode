from aiogram import Bot, Dispatcher

import asyncio
import datetime as dt

from app.core.config import AppConfig
from app.core.context import AppContext, set_context
from app.core.commands import get_default_bot_commands
from app.handlers import get_routers
from app.handlers.start import TosMiddleware
from app.services.admin_service import AdminPasswordService
from app.services.db import Database
from app.services.group_service import GroupResolver
from app.services.schedule_service import ScheduleService
from app.services.homework_service import HomeworkService
from app.services.schedule_watchdog import schedule_watchdog_loop


async def setup_bot(bot: Bot, dp: Dispatcher, config: AppConfig) -> None:
    db = Database(str(config.db_path))
    await db.init()
    group_resolver = GroupResolver(config.groups_path, config.group_aliases_path)
    schedule_service = ScheduleService(config.url_path)
    admin_service = AdminPasswordService(config.passwords_path)
    homework_service = HomeworkService(
        db=db,
        schedule_service=schedule_service,
        times_path=config.times_path,
        models_path=config.models_path,
        homeworks_dir=config.homeworks_dir,
        freeimage_api_key=config.freeimage_api_key,
        telegraph_token=config.telegraph_token,
    )
    ctx = AppContext(
        db=db,
        group_resolver=group_resolver,
        schedule_service=schedule_service,
        admin_service=admin_service,
        storage=dp.storage,
        homework_service=homework_service,
    )
    set_context(ctx)

    tz = dt.timezone(dt.timedelta(hours=3))
    asyncio.create_task(schedule_watchdog_loop(bot, tz))

    dp.message.middleware(TosMiddleware())
    dp.callback_query.middleware(TosMiddleware())
    for router in get_routers():
        dp.include_router(router)
    await bot.set_my_commands(get_default_bot_commands())
