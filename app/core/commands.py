from aiogram.types import BotCommand


def get_default_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="help", description="Справка"),
        BotCommand(command="setmygroup", description="Установить группу по умолчанию"),
        BotCommand(command="promo", description="Промокод"),
    ]


def get_admin_bot_commands(level: int) -> list[BotCommand]:
    commands = get_default_bot_commands()
    commands.append(BotCommand(command="adminpanel", description="Админ-панель"))
    commands.append(BotCommand(command="ai_logs", description="Логи AI домашки"))
    if level >= 2:
        commands.append(BotCommand(command="givepremium", description="Выдать премиум"))
    return commands

