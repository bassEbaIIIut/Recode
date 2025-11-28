import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties

from app.core.config import load_config
from app.core.bot import setup_bot
from app.core.fsm_storage import SQLiteStorage


async def main():
    config = load_config()
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    storage = SQLiteStorage(str(config.db_path))
    await storage.init()
    dp = Dispatcher(storage=storage)
    await setup_bot(bot, dp, config)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
