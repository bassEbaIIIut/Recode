from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def admin_main_keyboard(level: int) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    rows.append(
        [
            KeyboardButton(text="🧩 Система пользователей"),
            KeyboardButton(text="📊 Логи и статус"),
        ]
    )
    if level >= 2:
        rows.append([KeyboardButton(text="📚 Управление домашкой")])
        rows.append(
            [
                KeyboardButton(text="📅 Управление расписанием"),
                KeyboardButton(text="📢 Рассылка сообщений"),
            ]
        )
        rows.append(
            [
                KeyboardButton(text="🚫 Бан / Разбан"),
                KeyboardButton(text="⚙️ Настройка категорий"),
            ]
        )
        rows.append(
            [
                KeyboardButton(text="⚙️ Настройки рассылки"),
                KeyboardButton(text="⏏️ Выйти из панели"),
            ]
        )
    else:
        rows.append(
            [
                KeyboardButton(text="⚙️ Настройки рассылки"),
                KeyboardButton(text="⏏️ Выйти из панели"),
            ]
        )
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_user_system_keyboard(level: int) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = [
        [KeyboardButton(text="👥 Список всех пользователей")],
        [KeyboardButton(text="🔍 Поиск пользователя")],
    ]
    if level >= 3:
        keyboard.append([KeyboardButton(text="🧑‍💻 Сессии администраторов")])
    keyboard.append([KeyboardButton(text="⬅️ Назад в админ-меню")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_homework_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏳ Очередь предложенных ДЗ")],
            [KeyboardButton(text="🧠 AI Настройки")],
            [KeyboardButton(text="👮 Старосты")],
            [KeyboardButton(text="⬅️ Назад в админ-меню")],
        ],
        resize_keyboard=True,
    )


def admin_ai_settings_keyboard(auto_accept: bool) -> ReplyKeyboardMarkup:
    auto_text = "✅ Авто-принятие ВКЛ" if auto_accept else "⛔ Авто-принятие ВЫКЛ"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Обновить список моделей"), KeyboardButton(text="🤖 Выбрать модель")],
            [KeyboardButton(text="📝 Системный промт"), KeyboardButton(text=auto_text)],
            [KeyboardButton(text="⬅️ Назад в управление домашкой")],
        ],
        resize_keyboard=True,
    )


def admin_stewards_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Назначить старосту"), KeyboardButton(text="➖ Снять старосту")],
            [KeyboardButton(text="📋 Список старост")],
            [KeyboardButton(text="⬅️ Назад в управление домашкой")],
        ],
        resize_keyboard=True,
    )


def admin_pending_inline(req_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"hw_apr:{req_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"hw_rej:{req_id}"),
            ]
        ]
    )


def admin_models_inline(models: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for m in models:
        rows.append([InlineKeyboardButton(text=m, callback_data=f"ai_model:{m}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_users_inline_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    if total_pages < 1:
        total_pages = 1
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"admin_users_prev:{page}"),
                InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=f"admin_users_info:{page}"),
                InlineKeyboardButton(text="➡️", callback_data=f"admin_users_next:{page}"),
            ]
        ]
    )


def admin_sessions_keyboard(sessions: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for s in sessions:
        username = s.get("username") or ""
        if username:
            username_text = f"@{username}"
        else:
            username_text = f"ID {s.get('tg_id')}"
        level = s.get("level", 0)
        text = f"❌ {username_text} (lvl {level})"
        if len(text) > 64:
            text = text[:61] + "..."
        rows.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"admin_kill_session:{s['id']}",
                )
            ]
        )
    if rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data="admin_sessions_refresh",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить список",
                    callback_data="admin_sessions_refresh",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_schedule_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🔄 Перепарсить текущее")],
        [KeyboardButton(text="🗑 Удалить старые файлы")],
        [KeyboardButton(text="📋 Просмотреть активные подписки")],
        [KeyboardButton(text="⬅️ Назад в админ-меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_logs_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="⏱️ Показать uptime")],
        [KeyboardButton(text="📜 Показать последние N строк логов")],
        [KeyboardButton(text="🧠 Память и CPU")],
        [KeyboardButton(text="📥 Скачать весь лог")],
        [KeyboardButton(text="🧑‍💻 Логи ошибок людей")],
        [KeyboardButton(text="⬅️ Назад в админ-меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_ban_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🚫 Бан пользователя")],
        [KeyboardButton(text="✅ Разбан пользователя")],
        [KeyboardButton(text="📋 Список забаненных")],
        [KeyboardButton(text="⬅️ Назад в админ-меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_mailing_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🚫 Отключить рассылку для ID/@username")],
        [KeyboardButton(text="✅ Включить обратно ID/@username")],
        [KeyboardButton(text="📋 Показать исключения")],
        [KeyboardButton(text="⬅️ Назад в админ-меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)