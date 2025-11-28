import asyncio
import datetime as dt
import json
from html import escape
from pathlib import Path

import psutil
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    Message,
    CallbackQuery,
    BotCommandScopeChat,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from app.keyboards.admin import (
    admin_main_keyboard,
    admin_users_inline_keyboard,
    admin_sessions_keyboard,
    admin_user_system_keyboard,
    admin_schedule_keyboard,
    admin_logs_keyboard,
    admin_ban_keyboard,
    admin_mailing_keyboard,
    admin_homework_menu_keyboard,
    admin_ai_settings_keyboard,
    admin_stewards_keyboard,
    admin_pending_inline,
    admin_models_inline,
)
from app.core.states import MenuStates, AdminStates, AdminAuthStates
from app.core.commands import get_admin_bot_commands, get_default_bot_commands
from app.core.context import get_context
from app.keyboards.inline import broadcast_cancel_inline_keyboard
from app.keyboards.reply import main_menu_keyboard
from app.services.schedule_service import week_bounds_mon_sun, parse_schedule

router = Router()

MAX_ADMIN_LOGIN_ATTEMPTS = 3
ADMIN_LOGIN_BLOCK_MINUTES = 20

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = CONFIG_DIR / "bot.log"
FULL_LOG_PATH = CONFIG_DIR / "full_log.log"
USER_ERRORS_LOG_PATH = CONFIG_DIR / "user_errors.log"
CATEGORIES_PATH = CONFIG_DIR / "categories.json"
BROADCAST_BLOCKLIST_PATH = CONFIG_DIR / "broadcast_blocklist.json"
DEFAULT_CATEGORY_DISABLED_TEXT = "Функция временно недоступна."

BOT_START_TIME = dt.datetime.utcnow()


def _ensure_admin_files() -> None:
    if not LOG_PATH.exists():
        LOG_PATH.touch()
    if not USER_ERRORS_LOG_PATH.exists():
        USER_ERRORS_LOG_PATH.touch()
    if not BROADCAST_BLOCKLIST_PATH.exists():
        with BROADCAST_BLOCKLIST_PATH.open("w", encoding="utf-8") as f:
            json.dump({"ids": [], "usernames": []}, f, ensure_ascii=False, indent=2)
    if not CATEGORIES_PATH.exists():
        data = {
            "Расписание📋": {"enabled": True, "disabled_text": DEFAULT_CATEGORY_DISABLED_TEXT},
            "Домашка📚": {"enabled": True, "disabled_text": DEFAULT_CATEGORY_DISABLED_TEXT},
        }
        with CATEGORIES_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


_ensure_admin_files()


def _format_users_table(rows: list[dict], start_index: int) -> str:
    headers = ["№", "ID", "Username", "Группа", "Заблок.", "Админ"]
    body_rows: list[list[str]] = []
    for idx, u in enumerate(rows, start_index):
        body_rows.append(
            [
                str(idx),
                str(u.get("tg_id")),
                f"@{u.get('username')}" if u.get("username") else "@-",
                u.get("group_code") or "Нет",
                "Да" if u.get("is_blocked") else "Нет",
                "Да" if u.get("is_admin") else "Нет",
            ]
        )
    if not body_rows:
        return "📭 <b>Пользователи не найдены.</b>"
    all_rows = [headers] + body_rows
    col_widths = [0] * len(headers)
    for row in all_rows:
        for i, value in enumerate(row):
            col_widths[i] = max(col_widths[i], len(value))

    def make_border(left: str, middle: str, right: str) -> str:
        parts = []
        for w in col_widths:
            parts.append("─" * (w + 2))
        return left + middle.join(parts) + right

    def make_row(values: list[str]) -> str:
        parts = []
        for value, w in zip(values, col_widths):
            parts.append(" " + value.ljust(w) + " ")
        return "│" + "│".join(parts) + "│"

    table_lines: list[str] = []
    table_lines.append(make_border("┌", "┬", "┐"))
    table_lines.append(make_row(headers))
    table_lines.append(make_border("├", "┼", "┤"))
    for row in body_rows:
        table_lines.append(make_row(row))
    table_lines.append(make_border("└", "┴", "┘"))

    header_lines = [
        "👥 <b>Список пользователей</b>",
        "",
    ]
    return "\n".join(header_lines) + "\n<pre>\n" + "\n".join(table_lines) + "\n</pre>"


def _format_admin_sessions_text(sessions: list[dict]) -> str:
    if not sessions:
        return (
            "🧑‍💻 <b>Активные сессии администраторов</b>\n\n"
            "Сейчас нет активных сессий."
        )
    lines = ["🧑‍💻 <b>Активные сессии администраторов</b>", ""]
    for s in sessions:
        tg_id = s.get("tg_id")
        level = s.get("level")
        created_at = s.get("created_at")
        username = s.get("username") or ""
        if username:
            username_text = f"@{username}"
        else:
            username_text = "username не указан"
        name_parts = [s.get("first_name") or "", s.get("last_name") or ""]
        full_name = " ".join(p for p in name_parts if p).strip()
        if not full_name:
            full_name = "имя не указано"
        formatted_created = created_at
        try:
            dt_obj = dt.datetime.fromisoformat(created_at)
            formatted_created = dt_obj.strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass
        lines.append(
            f"• <code>{tg_id}</code> — {username_text}, {full_name}\n"
            f"  Уровень: <b>{level}</b>, сессия с: <code>{formatted_created}</code>"
        )
    return "\n".join(lines)


def _load_categories_config() -> dict:
    try:
        with CATEGORIES_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    changed = False
    if "Расписание📋" not in data:
        data["Расписание📋"] = {"enabled": True, "disabled_text": DEFAULT_CATEGORY_DISABLED_TEXT}
        changed = True
    if "Домашка📚" not in data:
        data["Домашка📚"] = {"enabled": True, "disabled_text": DEFAULT_CATEGORY_DISABLED_TEXT}
        changed = True
    if changed:
        _save_categories_config(data)
    return data


def _save_categories_config(data: dict) -> None:
    CATEGORIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CATEGORIES_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _categories_list_keyboard(categories: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for name in sorted(categories):
        rows.append([KeyboardButton(text=name)])
    rows.append([KeyboardButton(text="⬅️ Назад в админ-меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _category_menu_keyboard(enabled: bool) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if enabled:
        rows.append([KeyboardButton(text="⛔ Выключить")])
    else:
        rows.append([KeyboardButton(text="✅ Включить")])
    rows.append([KeyboardButton(text="✏️ Текст при отключении")])
    rows.append([KeyboardButton(text="🔙 Выбрать другую категорию")])
    rows.append([KeyboardButton(text="⬅️ Назад в админ-меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _load_broadcast_blocklist() -> dict:
    try:
        with BROADCAST_BLOCKLIST_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    ids = data.get("ids") or []
    usernames = data.get("usernames") or []
    ids_out: list[int] = []
    for v in ids:
        try:
            ids_out.append(int(v))
        except Exception:
            continue
    usernames_out: list[str] = []
    for u in usernames:
        if isinstance(u, str) and u:
            usernames_out.append(u.lower())
    return {"ids": ids_out, "usernames": usernames_out}


def _save_broadcast_blocklist(data: dict) -> None:
    ids = [int(v) for v in data.get("ids", [])]
    usernames = []
    for u in data.get("usernames", []):
        if isinstance(u, str) and u:
            usernames.append(u.lower())
    BROADCAST_BLOCKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BROADCAST_BLOCKLIST_PATH.open("w", encoding="utf-8") as f:
        json.dump({"ids": ids, "usernames": usernames}, f, ensure_ascii=False, indent=2)


async def _check_admin_block_before_login(message: Message) -> bool:
    ctx = get_context()
    limits = await ctx.db.get_admin_login_limits(message.from_user.id)
    if not limits:
        return False
    blocked_until_str = limits.get("blocked_until")
    if not blocked_until_str:
        return False
    try:
        blocked_until = dt.datetime.fromisoformat(blocked_until_str)
    except Exception:
        await ctx.db.clear_admin_login_limits(message.from_user.id)
        return False
    now = dt.datetime.utcnow()
    if blocked_until <= now:
        await ctx.db.clear_admin_login_limits(message.from_user.id)
        return False
    remaining = blocked_until - now
    seconds = int(remaining.total_seconds())
    minutes = max(1, seconds // 60 or 1)
    await message.answer(
        "🚫 <b>Вход в админ-панель временно заблокирован</b>\n\n"
        f"Попробуйте ещё раз через примерно <b>{minutes}</b> мин."
    )
    return True


async def _register_failed_admin_login(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    db = ctx.db
    now = dt.datetime.utcnow()
    limits = await db.get_admin_login_limits(message.from_user.id)
    attempts_left = MAX_ADMIN_LOGIN_ATTEMPTS
    if limits:
        blocked_until_str = limits.get("blocked_until")
        if blocked_until_str:
            try:
                blocked_until = dt.datetime.fromisoformat(blocked_until_str)
            except Exception:
                blocked_until = None
            if blocked_until and blocked_until > now:
                remaining = blocked_until - now
                seconds = int(remaining.total_seconds())
                minutes = max(1, seconds // 60 or 1)
                await message.answer(
                    "🚫 <b>Вход в админ-панель временно заблокирован</b>\n\n"
                    f"Попробуйте ещё раз через примерно <b>{minutes}</b> мин."
                )
                return
            else:
                limits = None
    if limits:
        attempts_left = int(limits.get("attempts_left", MAX_ADMIN_LOGIN_ATTEMPTS))
    new_attempts_left = attempts_left - 1
    if new_attempts_left <= 0:
        blocked_until = now + dt.timedelta(minutes=ADMIN_LOGIN_BLOCK_MINUTES)
        await db.set_admin_login_limits(
            message.from_user.id,
            attempts_left=0,
            blocked_until=blocked_until.isoformat(),
        )
        await message.answer(
            "🚫 <b>Вы исчерпали все попытки входа</b>.\n\n"
            f"Вход в админ-панель заблокирован на <b>{ADMIN_LOGIN_BLOCK_MINUTES}</b> минут."
        )
        await state.set_state(MenuStates.MAIN)
        await message.bot.set_my_commands(
            get_default_bot_commands(),
            scope=BotCommandScopeChat(chat_id=message.chat.id),
        )
        await message.answer(
            "Вы были возвращены в обычное меню.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await db.set_admin_login_limits(
        message.from_user.id,
        attempts_left=new_attempts_left,
        blocked_until=None,
    )
    await message.answer(
        "❌ <b>Неверный пароль.</b>\n"
        f"Осталось попыток: <b>{new_attempts_left}</b> из {MAX_ADMIN_LOGIN_ATTEMPTS}."
    )


async def _ensure_admin_session_message(message: Message, state: FSMContext, min_level: int = 1) -> dict | None:
    ctx = get_context()
    session = await ctx.db.get_active_admin_session_for_user(message.from_user.id)
    if not session:
        await state.set_state(MenuStates.MAIN)
        await message.bot.set_my_commands(
            get_default_bot_commands(),
            scope=BotCommandScopeChat(chat_id=message.chat.id),
        )
        await message.answer(
            "⚠️ <b>Сессия администратора недействительна.</b>\n"
            "Вы были возвращены в обычное меню.",
            reply_markup=main_menu_keyboard(),
        )
        return None
    if session.get("level", 0) < min_level:
        await message.answer("⛔ <b>Недостаточно прав</b> для выполнения этого действия.")
        return None
    return session


async def _ensure_admin_session_callback(callback: CallbackQuery, state: FSMContext, min_level: int = 1) -> dict | None:
    ctx = get_context()
    session = await ctx.db.get_active_admin_session_for_user(callback.from_user.id)
    if not session:
        await state.set_state(MenuStates.MAIN)
        await callback.bot.set_my_commands(
            get_default_bot_commands(),
            scope=BotCommandScopeChat(chat_id=callback.message.chat.id),
        )
        await callback.message.answer(
            "⚠️ <b>Сессия администратора недействительна.</b>\n"
            "Вы были возвращены в обычное меню.",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer()
        return None
    if session.get("level", 0) < min_level:
        await callback.answer("⛔ Недостаточно прав.", show_alert=True)
        return None
    return session


async def _process_admin_login(message: Message, state: FSMContext, password: str) -> None:
    password = (password or "").strip()
    if not password:
        await message.answer(
            "⚠️ Пароль не может быть пустым.\n"
            "Отправьте корректный пароль администратора одним сообщением."
        )
        return
    ctx = get_context()
    if ctx.admin_service is None:
        await state.clear()
        await state.set_state(MenuStates.MAIN)
        await message.bot.set_my_commands(
            get_default_bot_commands(),
            scope=BotCommandScopeChat(chat_id=message.chat.id),
        )
        await message.answer(
            "⚠️ <b>Админ-панель сейчас недоступна.</b>\n"
            "Вы были возвращены в обычное меню.",
            reply_markup=main_menu_keyboard(),
        )
        return
    level = ctx.admin_service.get_level_for_password(password)
    if not level:
        await _register_failed_admin_login(message, state)
        return
    await ctx.db.clear_admin_login_limits(message.from_user.id)
    existing_by_password = await ctx.db.get_active_admin_session_by_password(password)
    if existing_by_password and existing_by_password["tg_id"] != message.from_user.id:
        await message.answer(
            "⚠️ Данный пароль уже используется другим администратором.\n"
            "Дождитесь завершения его сессии."
        )
        return
    await ctx.db.deactivate_admin_sessions_for_user(message.from_user.id)
    await ctx.db.create_admin_session(message.from_user.id, level, password)
    await state.set_state(AdminStates.MAIN)
    await message.bot.set_my_commands(
        get_admin_bot_commands(level),
        scope=BotCommandScopeChat(chat_id=message.chat.id),
    )
    await message.answer(
        f"✅ <b>Вход в админ-панель выполнен.</b>\n"
        f"Ваш уровень доступа: <b>{level}</b>.",
        reply_markup=admin_main_keyboard(level),
    )


@router.message(Command("givepremium"))
async def cmd_givepremium(message: Message, command: CommandObject, state: FSMContext) -> None:
    ctx = get_context()
    session = await ctx.db.get_active_admin_session_for_user(message.from_user.id)
    if not session or session.get("level", 0) < 2:
        await message.answer("⛔ Команда доступна только администраторам уровня 2+.")
        return
    args = (command.args or "").strip()
    if not args:
        await message.answer(
            "Использование: <code>/givepremium @username 60d</code> или <code>/givepremium 123456789 15d</code>."
        )
        return
    parts = args.split()
    if len(parts) != 2:
        await message.answer(
            "Нужно указать пользователя и срок. Пример: <code>/givepremium @user 30d</code>."
        )
        return
    ident, period = parts
    if not period.endswith("d"):
        await message.answer("Срок указывается в днях, например: <code>30d</code>.")
        return
    try:
        days = int(period[:-1])
    except Exception:
        await message.answer("Неверный формат срока. Пример: <code>30d</code>.")
        return
    if days <= 0:
        await message.answer("Срок должен быть больше нуля.")
        return
    tg_id: int | None = None
    if ident.lstrip("@").isdigit():
        tg_id = int(ident.lstrip("@"))
    else:
        username = ident.lstrip("@").lower()
        users = await ctx.db.search_users(username)
        if not users:
            await message.answer("Пользователь с таким username не найден в базе.")
            return
        tg_id = users[0].get("tg_id")
    if not tg_id:
        await message.answer("Не удалось определить ID пользователя.")
        return
    until = dt.datetime.utcnow() + dt.timedelta(days=days)
    await ctx.db.set_user_premium(tg_id, until)
    until_str = until.strftime("%d.%m.%Y")
    await message.answer(
        f"✅ Премиум выдан пользователю <code>{tg_id}</code> до <b>{until_str}</b>."
    )


@router.message(Command("ai_logs"))
async def cmd_ai_logs(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    session = await ctx.db.get_active_admin_session_for_user(message.from_user.id)
    if not session:
        await message.answer("⛔ Доступно только администраторам.")
        return
    page = 1
    logs, total, pages = ctx.homework_service.load_ai_logs_page(page, per_page=5)
    if total == 0:
        await message.answer("Логи AI-проверки домашки пусты.")
        return
    lines: list[str] = ["🧠 <b>Логи AI-проверки домашки</b>", ""]
    for item in logs:
        user_id = item.get("user_id")
        username = item.get("username")
        full_name = item.get("full_name")
        subject = item.get("subject")
        text = item.get("text")
        telegraph_url = item.get("telegraph_url")
        ai_res = item.get("ai_result") or {}
        decision = ai_res.get("decision")
        raw = ai_res.get("raw")
        user_line = f"ID: <code>{user_id}</code>"
        if username:
            user_line += f" (@{username})"
        if full_name:
            user_line += f" — {escape(full_name)}"
        lines.append(user_line)
        lines.append(f"Предмет: <b>{escape(subject or '')}</b>")
        lines.append(f"Текст: {escape(text or '')}")
        if telegraph_url:
            lines.append(f"Фото: {escape(telegraph_url)}")
        lines.append(f"Ответ нейросети: {escape(str(raw)[:800])}")
        lines.append("")
    lines.append(f"Показана страница 1 из {pages}. Поддержка постраничной навигации будет добавлена отдельно.")
    await message.answer("\n".join(lines))


@router.message(Command("adminpanel"))
async def cmd_adminpanel(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    admin_session = await ctx.db.get_active_admin_session_for_user(message.from_user.id)
    if admin_session:
        await state.set_state(AdminStates.MAIN)
        await message.bot.set_my_commands(
            get_admin_bot_commands(admin_session["level"]),
            scope=BotCommandScopeChat(chat_id=message.chat.id),
        )
        await message.answer(
            "🛠 <b>Админ-панель уже активна.</b>\n"
            "Используйте кнопки меню ниже.",
            reply_markup=admin_main_keyboard(admin_session["level"]),
        )
        return
    if await _check_admin_block_before_login(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        await _process_admin_login(message, state, parts[1])
        return
    await state.set_state(AdminAuthStates.waiting_for_password)
    await message.answer(
        "<b>Вход в админ-панель</b>\n\n"
        "Отправьте пароль администратора одним сообщением."
    )


@router.message(AdminAuthStates.waiting_for_password)
async def adminpanel_password_input(message: Message, state: FSMContext) -> None:
    await _process_admin_login(message, state, message.text or "")


@router.message(AdminStates.MAIN, F.text == "📚 Управление домашкой")
async def admin_homework_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.HOMEWORK_MENU)
    await message.answer("📚 <b>Управление домашкой</b>", reply_markup=admin_homework_menu_keyboard())


@router.message(AdminStates.HOMEWORK_MENU, F.text == "⬅️ Назад в админ-меню")
async def admin_homework_back(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.MAIN)
    await message.answer("Главное меню", reply_markup=admin_main_keyboard(session["level"]))


@router.message(AdminStates.HOMEWORK_MENU, F.text == "🧠 AI Настройки")
async def admin_ai_settings(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    ctx = get_context()
    config = ctx.homework_service.load_ai_config()
    auto_accept = config.get("auto_accept", False)
    await state.set_state(AdminStates.HOMEWORK_AI_MENU)
    await message.answer(
        f"🧠 <b>AI Настройки</b>\n\nМодель: {config.get('model')}\nТемпература: {config.get('temperature')}\nАвто-принятие: {auto_accept}",
        reply_markup=admin_ai_settings_keyboard(auto_accept)
    )


@router.message(AdminStates.HOMEWORK_AI_MENU, F.text == "📝 Системный промт")
async def admin_ai_edit_prompt(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    config = ctx.homework_service.load_ai_config()
    await state.set_state(AdminStates.HOMEWORK_AI_EDIT_PROMPT)
    await message.answer(f"Текущий промт:\n<code>{config.get('system_prompt')}</code>\n\nВведите новый промт:")


@router.message(AdminStates.HOMEWORK_AI_EDIT_PROMPT)
async def admin_ai_save_prompt(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    config = ctx.homework_service.load_ai_config()
    config["system_prompt"] = message.text
    ctx.homework_service.save_ai_config(config)
    await state.set_state(AdminStates.HOMEWORK_AI_MENU)
    await message.answer("Промт обновлен", reply_markup=admin_ai_settings_keyboard(config.get("auto_accept")))


@router.message(AdminStates.HOMEWORK_AI_MENU, F.text.contains("Авто-принятие"))
async def admin_ai_toggle_auto(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    config = ctx.homework_service.load_ai_config()
    config["auto_accept"] = not config.get("auto_accept", False)
    ctx.homework_service.save_ai_config(config)
    await message.answer("Настройка изменена", reply_markup=admin_ai_settings_keyboard(config["auto_accept"]))


@router.message(AdminStates.HOMEWORK_AI_MENU, F.text == "🔄 Обновить список моделей")
async def admin_ai_refresh_models(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    await message.answer("Обновление списка...")
    models = await ctx.homework_service.pollinations_refresh_models()
    await message.answer(f"Загружено {len(models)} моделей.")


@router.message(AdminStates.HOMEWORK_AI_MENU, F.text == "🤖 Выбрать модель")
async def admin_ai_select_model(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    models = ctx.homework_service.load_models()
    if not models:
        models = await ctx.homework_service.pollinations_refresh_models()
    await message.answer("Выберите модель:", reply_markup=admin_models_inline(models[:10]))


@router.callback_query(F.data.startswith("ai_model:"))
async def admin_ai_model_callback(callback: CallbackQuery, state: FSMContext) -> None:
    model = callback.data.split(":", 1)[1]
    ctx = get_context()
    config = ctx.homework_service.load_ai_config()
    config["model"] = model
    ctx.homework_service.save_ai_config(config)
    await callback.answer(f"Модель {model} выбрана")
    await callback.message.delete()


@router.message(AdminStates.HOMEWORK_AI_MENU, F.text == "⬅️ Назад в управление домашкой")
async def admin_ai_back_to_homework(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.HOMEWORK_MENU)
    await message.answer("📚 Управление домашкой", reply_markup=admin_homework_menu_keyboard())


@router.message(AdminStates.HOMEWORK_MENU, F.text == "⏳ Очередь предложенных ДЗ")
async def admin_homework_queue(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    items, total, pages = ctx.homework_service.load_public_pending_page(1)
    if not items:
        await message.answer("Очередь пуста")
        return
    for item in items:
        text = f"Предложил: {item.get('username')}\nПредмет: {item.get('subject')}\nТекст: {item.get('text')}\nAI: {item.get('ai_result', {}).get('raw')}"
        await message.answer(text, reply_markup=admin_pending_inline(item["id"]))


@router.callback_query(F.data.startswith("hw_apr:"))
async def admin_approve_hw(callback: CallbackQuery) -> None:
    req_id = callback.data.split(":")[1]
    ctx = get_context()
    item = ctx.homework_service.get_pending_request(req_id)
    if item:
        ctx.homework_service.add_public_homework(
            item["group_code"],
            item["subject"],
            item["text"],
            item["telegraph_url"],
        )
        ctx.homework_service.remove_pending_request(req_id)
        await callback.message.edit_text("✅ Одобрено")
    else:
        await callback.answer("Заявка не найдена")


@router.callback_query(F.data.startswith("hw_rej:"))
async def admin_reject_hw(callback: CallbackQuery) -> None:
    req_id = callback.data.split(":")[1]
    ctx = get_context()
    ctx.homework_service.remove_pending_request(req_id)
    await callback.message.edit_text("❌ Отклонено")


@router.message(AdminStates.HOMEWORK_MENU, F.text == "👮 Старосты")
async def admin_stewards_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.HOMEWORK_STEWARDS_MENU)
    await message.answer("Управление старостами", reply_markup=admin_stewards_keyboard())


@router.message(AdminStates.HOMEWORK_STEWARDS_MENU, F.text == "➕ Назначить старосту")
async def admin_stewards_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminStates.HOMEWORK_STEWARDS_ADD)
    await message.answer("Введите ID или Username пользователя и код группы. Пример: @user ИС-131")


@router.message(AdminStates.HOMEWORK_STEWARDS_ADD)
async def admin_stewards_add_process(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    if text == "⬅️ Назад в управление домашкой":
        session = await _ensure_admin_session_message(message, state, min_level=2)
        if not session:
            return
        await state.set_state(AdminStates.HOMEWORK_MENU)
        await message.answer("📚 Управление домашкой", reply_markup=admin_homework_menu_keyboard())
        return
    parts = text.split()
    if len(parts) < 2:
        await message.answer("Неверный формат. Пример: @user ИС-131")
        return
    ident, group = parts[0], parts[1]
    ctx = get_context()
    if ident.lstrip("@").isdigit():
        uid = int(ident.lstrip("@"))
    else:
        users = await ctx.db.search_users(ident)
        if not users:
            await message.answer("Пользователь не найден")
            return
        uid = users[0]["tg_id"]
    await ctx.db.set_steward(uid, group)
    await message.answer(f"Староста для {group} назначен")
    await state.set_state(AdminStates.HOMEWORK_STEWARDS_MENU)
    await message.answer("Управление старостами", reply_markup=admin_stewards_keyboard())


@router.message(AdminStates.HOMEWORK_STEWARDS_MENU, F.text == "➖ Снять старосту")
async def admin_stewards_remove_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminStates.HOMEWORK_STEWARDS_REMOVE)
    await message.answer("Введите ID или Username пользователя, которого нужно снять с роли старосты.")


@router.message(AdminStates.HOMEWORK_STEWARDS_REMOVE)
async def admin_stewards_remove_process(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text == "⬅️ Назад в управление домашкой":
        session = await _ensure_admin_session_message(message, state, min_level=2)
        if not session:
            return
        await state.set_state(AdminStates.HOMEWORK_MENU)
        await message.answer("📚 Управление домашкой", reply_markup=admin_homework_menu_keyboard())
        return
    if not text:
        await message.answer("Укажите ID или username пользователя.")
        return
    ctx = get_context()
    if text.lstrip("@").isdigit():
        uid = int(text.lstrip("@"))
    else:
        users = await ctx.db.search_users(text)
        if not users:
            await message.answer("Пользователь не найден.")
            return
        uid = users[0]["tg_id"]
    await ctx.db.remove_steward(uid)
    await state.set_state(AdminStates.HOMEWORK_STEWARDS_MENU)
    await message.answer("Староста снят.", reply_markup=admin_stewards_keyboard())


@router.message(AdminStates.HOMEWORK_STEWARDS_MENU, F.text == "📋 Список старост")
async def admin_stewards_list(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    ctx = get_context()
    items = await ctx.db.list_stewards()
    if not items:
        await message.answer("Список старост пуст.", reply_markup=admin_stewards_keyboard())
        return
    lines = ["📋 <b>Список старост</b>", ""]
    for item in items:
        tg_id = item.get("tg_id")
        group_code = item.get("group_code")
        username = item.get("username")
        first_name = item.get("first_name") or ""
        last_name = item.get("last_name") or ""
        name = " ".join(p for p in [first_name, last_name] if p).strip()
        ident = f"<code>{tg_id}</code>"
        if username:
            ident += f" (@{username})"
        if name:
            ident += f" — {escape(name)}"
        lines.append(f"{ident} — группа <b>{escape(str(group_code))}</b>")
    await message.answer("\n".join(lines), reply_markup=admin_stewards_keyboard())


@router.message(
    AdminStates.HOMEWORK_STEWARDS_MENU,
    F.text == "⬅️ Назад в управление домашкой",
)
@router.message(
    AdminStates.HOMEWORK_STEWARDS_ADD,
    F.text == "⬅️ Назад в управление домашкой",
)
@router.message(
    AdminStates.HOMEWORK_STEWARDS_REMOVE,
    F.text == "⬅️ Назад в управление домашкой",
)
async def admin_stewards_back_to_homework(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.HOMEWORK_MENU)
    await message.answer("📚 Управление домашкой", reply_markup=admin_homework_menu_keyboard())


@router.message(AdminStates.MAIN, F.text == "🧩 Система пользователей")
async def admin_user_system_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    level = session.get("level", 1)
    await state.set_state(AdminStates.USER_SYSTEM_MENU)
    await message.answer(
        "👥 <b>Система пользователей</b>\n\n"
        "Выберите нужный раздел:",
        reply_markup=admin_user_system_keyboard(level),
    )


@router.message(AdminStates.USER_SYSTEM_MENU, F.text == "⬅️ Назад в админ-меню")
async def admin_user_system_back(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    level = session.get("level", 1)
    await state.set_state(AdminStates.MAIN)
    await message.answer(
        "🔙 Вы вернулись в главное меню админ-панели.",
        reply_markup=admin_main_keyboard(level),
    )


@router.message(AdminStates.USER_SYSTEM_MENU, F.text == "👥 Список всех пользователей")
async def admin_users_list(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    ctx = get_context()
    page = 1
    per_page = 20
    users, total, pages = await ctx.db.list_users_page(page, per_page)
    if not users or total == 0:
        await message.answer("📭 <b>Список пользователей пуст.</b>")
        return
    text = _format_users_table(users, start_index=1)
    markup = admin_users_inline_keyboard(page, pages)
    await message.answer(text, reply_markup=markup)


@router.message(AdminStates.USER_SYSTEM_MENU, F.text == "🔍 Поиск пользователя")
async def admin_search_start(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    await state.set_state(AdminStates.USER_SEARCH)
    await message.answer(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Отправьте username (с @ или без) или числовой ID пользователя."
    )


@router.message(AdminStates.USER_SEARCH)
async def admin_search_process(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    query = (message.text or "").strip()
    if not query:
        await message.answer("⚠️ Введите непустой запрос для поиска.")
        return
    ctx = get_context()
    users = await ctx.db.search_users(query)
    if not users:
        await message.answer("📭 <b>Пользователи по заданному запросу не найдены.</b>")
        await state.set_state(AdminStates.USER_SYSTEM_MENU)
        return
    user = users[0]
    name_parts = [user.get("first_name") or "", user.get("last_name") or ""]
    full_name = " ".join(p for p in name_parts if p).strip() or "не указано"
    username_text = f"@{user['username']}" if user.get("username") else "не указано"
    group_text = user.get("group_code") or "Нет"
    blocked_text = "Да" if user.get("is_blocked") else "Нет"
    admin_text = "Да" if user.get("is_admin") else "Нет"
    lines = [
        "👤 <b>Информация о пользователе</b>",
        f"Имя: <b>{full_name}</b>",
        f"Username: {username_text}",
        f"ID: <code>{user['tg_id']}</code>",
        f"Группа: <b>{group_text}</b>",
        f"Заблокировал бота: <b>{blocked_text}</b>",
        f"Активный админ: <b>{admin_text}</b>",
    ]
    if len(users) > 1:
        lines.append("")
        lines.append(f"Показан первый из <b>{len(users)}</b> найденных пользователей.")
    await message.answer("\n".join(lines))
    await state.set_state(AdminStates.USER_SYSTEM_MENU)


@router.message(AdminStates.USER_SYSTEM_MENU, F.text == "🧑‍💻 Сессии администраторов")
async def admin_sessions_view(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=3)
    if not session:
        return
    ctx = get_context()
    sessions = await ctx.db.get_active_admin_sessions_with_users()
    text = _format_admin_sessions_text(sessions)
    markup = admin_sessions_keyboard(sessions)
    await message.answer(text, reply_markup=markup)


@router.message(AdminStates.MAIN, F.text == "📅 Управление расписанием")
async def admin_schedule_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.SCHEDULE_MENU)
    await message.answer(
        "📅 <b>Управление расписанием</b>\n\nВыберите действие:",
        reply_markup=admin_schedule_keyboard(),
    )


@router.message(AdminStates.SCHEDULE_MENU, F.text == "⬅️ Назад в админ-меню")
async def admin_schedule_back(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    level = session.get("level", 1)
    await state.set_state(AdminStates.MAIN)
    await message.answer(
        "🔙 Вы вернулись в главное меню админ-панели.",
        reply_markup=admin_main_keyboard(level),
    )


@router.message(AdminStates.SCHEDULE_MENU, F.text == "📋 Просмотреть активные подписки")
async def admin_schedule_show_subscriptions(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    ctx = get_context()
    url_map = getattr(ctx.schedule_service, "url_map", {}) or {}
    if not url_map:
        await message.answer("📭 Активных подписок на расписание нет.")
        return
    lines = ["📋 <b>Активные подписки на расписание</b>", ""]
    for group, url in sorted(url_map.items()):
        lines.append(f"<b>{escape(group)}</b>: <code>{escape(url)}</code>")
    await message.answer("\n".join(lines))


@router.message(AdminStates.SCHEDULE_MENU, F.text == "🗑 Удалить старые файлы")
async def admin_schedule_cleanup_files(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    ctx = get_context()
    schedule_service = ctx.schedule_service
    schedule_dir = getattr(schedule_service, "schedule_dir", None)
    if schedule_dir is None:
        await message.answer("⚠️ Директория с расписанием не найдена.")
        return
    now_ts = dt.datetime.now().timestamp()
    threshold = now_ts - 10 * 24 * 60 * 60
    deleted = 0
    for path in Path(schedule_dir).glob("*.json"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < threshold:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                continue
    if deleted == 0:
        await message.answer("Старых файлов расписания не найдено.")
    else:
        await message.answer(f"Удалено старых файлов расписания: <b>{deleted}</b>.")


@router.message(AdminStates.SCHEDULE_MENU, F.text == "🔄 Перепарсить текущее")
async def admin_schedule_reparse_current(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    ctx = get_context()
    schedule_service = ctx.schedule_service
    url_map = getattr(schedule_service, "url_map", {}) or {}
    if not url_map:
        await message.answer("📭 Нет групп с настроенными URL расписания.")
        return
    await message.answer("🔄 Начинаю перепарсивание расписания для всех групп. Это может занять время.")
    today = dt.date.today()
    monday, sunday = week_bounds_mon_sun(today)
    success = 0
    errors = 0
    for group_code, url in url_map.items():
        if not url:
            continue
        try:
            schedule = await asyncio.to_thread(parse_schedule, url)
            if schedule:
                schedule_service._save_schedule(group_code, today, schedule)
                success += 1
            else:
                errors += 1
        except Exception:
            errors += 1
    if success == 0:
        await message.answer(
            f"⚠️ Не удалось получить расписание ни для одной группы за период {monday.strftime('%d.%m.%Y')}–{sunday.strftime('%d.%m.%Y')}."
        )
    else:
        await message.answer(
            f"✅ Перепарсивание завершено.\n"
            f"Успешно групп: <b>{success}</b>\n"
            f"Ошибок: <b>{errors}</b>"
        )


@router.message(AdminStates.MAIN, F.text == "📊 Логи и статус")
async def admin_logs_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    await state.set_state(AdminStates.LOGS_MENU)
    await message.answer(
        "📊 <b>Логи и системный статус</b>\n\nВыберите действие:",
        reply_markup=admin_logs_keyboard(),
    )


@router.message(AdminStates.LOGS_MENU, F.text == "⬅️ Назад в админ-меню")
async def admin_logs_back(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    level = session.get("level", 1)
    await state.set_state(AdminStates.MAIN)
    await message.answer(
        "🔙 Вы вернулись в главное меню админ-панели.",
        reply_markup=admin_main_keyboard(level),
    )


@router.message(AdminStates.LOGS_MENU, F.text == "⏱️ Показать uptime")
async def admin_show_uptime(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    now = dt.datetime.utcnow()
    delta = now - BOT_START_TIME
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    rem = total_seconds % 86400
    hours = rem // 3600
    rem %= 3600
    minutes = rem // 60
    seconds = rem % 60
    parts = []
    if days:
        parts.append(f"{days} д")
    if hours or days:
        parts.append(f"{hours} ч")
    if minutes or hours or days:
        parts.append(f"{minutes} мин")
    parts.append(f"{seconds} с")
    text = "⏱️ <b>Время работы бота</b>\n\n" + " ".join(parts)
    await message.answer(text)


@router.message(AdminStates.LOGS_MENU, F.text == "📜 Показать последние N строк логов")
async def admin_logs_ask_lines(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    await state.set_state(AdminStates.LOGS_WAIT_LINES)
    await message.answer(
        "Введите число N — сколько последних строк из системного лога показать.\nНапример: <code>100</code>"
    )


@router.message(AdminStates.LOGS_WAIT_LINES)
async def admin_logs_show_lines(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    text_raw = (message.text or "").strip()
    if not text_raw.isdigit():
        await message.answer("Введите положительное число.")
        return
    n = int(text_raw)
    if n <= 0:
        await message.answer("Число должно быть больше нуля.")
        return
    if n > 2000:
        n = 2000
    if not LOG_PATH.exists():
        await state.set_state(AdminStates.LOGS_MENU)
        await message.answer(
            "Файл системного лога не найден.",
            reply_markup=admin_logs_keyboard(),
        )
        return
    with LOG_PATH.open(encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    tail = "".join(lines[-n:])
    payload = escape(tail)
    await message.answer(
        f"📜 <b>Последние {n} строк системного лога</b>:\n<pre>{payload}</pre>"
    )
    await state.set_state(AdminStates.LOGS_MENU)
    await message.answer("Выберите дальнейшее действие:", reply_markup=admin_logs_keyboard())


@router.message(AdminStates.LOGS_MENU, F.text == "🧠 Память и CPU")
async def admin_logs_resources(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    cpu_percents = psutil.cpu_percent(percpu=True)
    cpu_lines = []
    for idx, val in enumerate(cpu_percents, 1):
        cpu_lines.append(f"Ядро {idx}: {val:.1f}%")
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    proc = psutil.Process()
    pmem = proc.memory_info()
    mb = 1024 * 1024
    ram_lines = [
        f"Всего: {vm.total / mb:.1f} МБ",
        f"Использовано: {vm.used / mb:.1f} МБ ({vm.percent:.1f}%)",
        f"Свободно: {vm.available / mb:.1f} МБ",
        f"Процесс бота (RSS): {pmem.rss / mb:.1f} МБ",
    ]
    swap_lines = [
        f"Всего: {swap.total / mb:.1f} МБ",
        f"Использовано: {swap.used / mb:.1f} МБ ({swap.percent:.1f}%)",
        f"Свободно: {(swap.total - swap.used) / mb:.1f} МБ",
    ]
    config_path = BASE_DIR / "config"
    disk = psutil.disk_usage(str(config_path))
    gb = 1024 * 1024 * 1024
    disk_lines = [
        f"Всего: {disk.total / gb:.2f} ГБ",
        f"Использовано: {disk.used / gb:.2f} ГБ ({disk.percent:.1f}%)",
        f"Свободно: {disk.free / gb:.2f} ГБ",
    ]
    text = (
        "🧠 <b>Память и CPU</b>\n\n"
        "CPU по ядрам:\n<pre>\n" + "\n".join(cpu_lines) + "\n</pre>\n\n"
        "RAM:\n<pre>\n" + "\n".join(ram_lines) + "\n</pre>\n\n"
        "Swap:\n<pre>\n" + "\n".join(swap_lines) + "\n</pre>\n\n"
        f"Диск для config/ ({config_path}):\n<pre>\n" + "\n".join(disk_lines) + "\n</pre>"
    )
    await message.answer(text)


@router.message(AdminStates.LOGS_MENU, F.text == "📥 Скачать весь лог")
async def admin_logs_download(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    lines_out: list[str] = []
    if LOG_PATH.exists():
        with LOG_PATH.open(encoding="utf-8", errors="ignore") as f:
            system_lines = f.read().splitlines()
        if system_lines:
            lines_out.append("===== SYSTEM LOG =====")
            lines_out.extend(system_lines)
    entries: list[dict] = []
    if USER_ERRORS_LOG_PATH.exists():
        with USER_ERRORS_LOG_PATH.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if isinstance(data, dict):
                    entries.append(data)
    if entries:
        if lines_out:
            lines_out.append("")
            lines_out.append("")
        lines_out.append("===== USER ERRORS =====")
        for item in entries:
            ts = item.get("timestamp") or ""
            user_id = item.get("user_id") or item.get("tg_id")
            username = item.get("username") or ""
            text_val = item.get("text")
            data_val = item.get("data")
            action = item.get("action")
            if not action:
                if data_val:
                    action = f"callback: {data_val}"
                elif text_val:
                    action = f"message: {text_val}"
                else:
                    action = ""
            err = item.get("error") or ""
            tb = item.get("traceback") or ""
            lines_out.append(f"[{ts}] user_id={user_id} username={username}")
            if action:
                lines_out.append(f"action: {action}")
            if err:
                lines_out.append(f"error: {err}")
            if tb:
                lines_out.append(tb)
            lines_out.append("")
    if not lines_out:
        await message.answer("Логи пока пусты.")
        return
    with FULL_LOG_PATH.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines_out))
    file = FSInputFile(str(FULL_LOG_PATH))
    await message.answer_document(file, caption="Полный лог бота (системный и ошибки пользователей).")


@router.message(AdminStates.LOGS_MENU, F.text == "🧑‍💻 Логи ошибок людей")
async def admin_logs_user_errors_ask(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    await state.set_state(AdminStates.LOGS_WAIT_USER_ERRORS_LINES)
    await message.answer(
        "Введите число N — сколько последних ошибок пользователей показать.\nНапример: <code>50</code>"
    )


@router.message(AdminStates.LOGS_WAIT_USER_ERRORS_LINES)
async def admin_logs_user_errors_show(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    text_raw = (message.text or "").strip()
    if not text_raw.isdigit():
        await message.answer("Введите положительное число.")
        return
    n = int(text_raw)
    if n <= 0:
        await message.answer("Число должно быть больше нуля.")
        return
    if n > 1000:
        n = 1000
    if not USER_ERRORS_LOG_PATH.exists():
        await state.set_state(AdminStates.LOGS_MENU)
        await message.answer(
            "Файл логов ошибок пользователей не найден.",
            reply_markup=admin_logs_keyboard(),
        )
        return
    entries: list[dict] = []
    with USER_ERRORS_LOG_PATH.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            if isinstance(data, dict):
                entries.append(data)
    tail = entries[-n:]
    if not tail:
        await state.set_state(AdminStates.LOGS_MENU)
        await message.answer(
            "Записей об ошибках пользователей не найдено.",
            reply_markup=admin_logs_keyboard(),
        )
        return
    lines_out: list[str] = ["🧑‍💻 <b>Последние ошибки пользователей</b>", ""]
    for item in tail:
        ts = item.get("timestamp") or ""
        user_id = item.get("user_id") or item.get("tg_id")
        username = item.get("username")
        text_val = item.get("text")
        data_val = item.get("data")
        action = item.get("action")
        if not action:
            if data_val:
                action = f"callback: {data_val}"
            elif text_val:
                action = f"message: {text_val}"
            else:
                action = ""
        err = item.get("error") or ""
        tb = item.get("traceback") or ""
        username_text = f"@{username}" if username else "-"
        lines_out.append(
            f"⏱ {escape(str(ts))}\n"
            f"👤 ID: <code>{user_id}</code>, {escape(username_text)}\n"
            f"⚙ Действие: <code>{escape(str(action))}</code>\n"
            f"❌ Ошибка: <code>{escape(str(err))}</code>\n"
            f"🧵 Traceback:\n<pre>{escape(str(tb))}</pre>\n"
        )
    await message.answer("\n".join(lines_out))
    await state.set_state(AdminStates.LOGS_MENU)
    await message.answer("Выберите дальнейшее действие:", reply_markup=admin_logs_keyboard())


@router.message(AdminStates.MAIN, F.text == "📢 Рассылка сообщений")
async def admin_broadcast_start(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.BROADCAST_WAIT_MESSAGE)
    await message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Отправьте сообщение, которое нужно разослать всем пользователям.\n"
        "Можно отправить текст, фото, файл и т.п.\n\n"
        "Для отмены рассылки используйте кнопку ниже.",
        reply_markup=broadcast_cancel_inline_keyboard(),
    )


@router.message(AdminStates.BROADCAST_WAIT_MESSAGE)
async def admin_broadcast_process(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    ctx = get_context()
    users = await ctx.db.get_all_users_for_broadcast()
    blocklist = _load_broadcast_blocklist()
    blocked_ids = set(blocklist.get("ids", []))
    blocked_usernames = set(blocklist.get("usernames", []))
    sent = 0
    errors = 0
    for u in users:
        tg_id = u.get("tg_id")
        if not tg_id:
            continue
        if tg_id == message.chat.id:
            continue
        username = u.get("username")
        if tg_id in blocked_ids:
            continue
        if username and username.lower() in blocked_usernames:
            continue
        if u.get("is_blocked"):
            continue
        banned = await ctx.db.is_user_banned(tg_id, username)
        if banned:
            continue
        try:
            await message.bot.copy_message(
                chat_id=tg_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            sent += 1
        except Exception:
            errors += 1
            await ctx.db.set_user_blocked(tg_id, True)
    level = session.get("level", 1)
    await state.set_state(AdminStates.MAIN)
    await message.answer(
        f"📢 Рассылка завершена.\n\n"
        f"Успешно отправлено: <b>{sent}</b>\n"
        f"Ошибок при отправке: <b>{errors}</b>",
        reply_markup=admin_main_keyboard(level),
    )


@router.message(AdminStates.MAIN, F.text == "🚫 Бан / Разбан")
async def admin_ban_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.BAN_MENU)
    await message.answer(
        "🚫 <b>Бан / Разбан пользователей</b>\n\nВыберите действие:",
        reply_markup=admin_ban_keyboard(),
    )


@router.message(AdminStates.BAN_MENU, F.text == "⬅️ Назад в админ-меню")
async def admin_ban_back(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    level = session.get("level", 1)
    await state.set_state(AdminStates.MAIN)
    await message.answer(
        "🔙 Вы вернулись в главное меню админ-панели.",
        reply_markup=admin_main_keyboard(level),
    )


@router.message(AdminStates.BAN_MENU, F.text == "📋 Список забаненных")
async def admin_ban_list(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    ctx = get_context()
    banned = await ctx.db.get_banned_users()
    if not banned:
        await message.answer("📭 Список забаненных пуст.")
        return
    lines = ["🚫 <b>Список забаненных пользователей</b>", ""]
    for item in banned:
        tg_id = item.get("tg_id")
        username = item.get("username")
        reason = item.get("reason") or "-"
        if username:
            ident = f"@{username}"
            if tg_id:
                ident = f"{tg_id} / {ident}"
        else:
            ident = str(tg_id) if tg_id else "не указан"
        lines.append(f"{escape(ident)}: {escape(str(reason))}")
    await message.answer("\n".join(lines))


@router.message(AdminStates.BAN_MENU, F.text == "🚫 Бан пользователя")
async def admin_ban_start(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.BAN_WAIT_USER)
    await message.answer(
        "Отправьте ID или @username и причину бана в одном сообщении.\n"
        "Пример: <code>123456 Спам</code> или <code>@user Оскорбления</code>."
    )


@router.message(AdminStates.BAN_WAIT_USER)
async def admin_ban_process(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    text_raw = (message.text or "").strip()
    if not text_raw:
        await message.answer("Введите ID или username и причину.")
        return
    parts = text_raw.split(maxsplit=1)
    ident = parts[0]
    reason = parts[1].strip() if len(parts) > 1 else "Без причины"
    ctx = get_context()
    tg_id: int | None
    username: str | None
    if ident.lstrip("@").isdigit():
        tg_id = int(ident.lstrip("@"))
        username = None
        user = await ctx.db.get_user(tg_id)
        if user and user.get("username"):
            username = user["username"]
    else:
        username = ident.lstrip("@")
        user_list = await ctx.db.search_users(username)
        if user_list:
            tg_id = user_list[0].get("tg_id")
            username = user_list[0].get("username") or username
        else:
            tg_id = None
    await ctx.db.ban_user(tg_id, username, reason)
    await state.set_state(AdminStates.BAN_MENU)
    await message.answer("Пользователь добавлен в бан-лист.", reply_markup=admin_ban_keyboard())


@router.message(AdminStates.BAN_MENU, F.text == "✅ Разбан пользователя")
async def admin_unban_start(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await state.set_state(AdminStates.UNBAN_WAIT_USER)
    await message.answer(
        "Отправьте ID или @username пользователя, которого нужно разбанить."
    )


@router.message(AdminStates.UNBAN_WAIT_USER)
async def admin_unban_process(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    text_raw = (message.text or "").strip()
    if not text_raw:
        await message.answer("Введите ID или username.")
        return
    ident = text_raw
    ctx = get_context()
    affected = 0
    if ident.lstrip("@").isdigit():
        tg_id = int(ident.lstrip("@"))
        affected = await ctx.db.unban_by_tg_id(tg_id)
    else:
        username = ident.lstrip("@")
        affected = await ctx.db.unban_by_username(username)
    await state.set_state(AdminStates.BAN_MENU)
    if affected == 0:
        await message.answer("Пользователь не найден в списке банов.", reply_markup=admin_ban_keyboard())
    else:
        await message.answer("Пользователь разбанен.", reply_markup=admin_ban_keyboard())


@router.message(AdminStates.MAIN, F.text == "⚙️ Настройка категорий")
async def admin_categories_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    cfg = _load_categories_config()
    await state.set_state(AdminStates.CATEGORIES_SELECT)
    lines = ["⚙️ <b>Настройка категорий</b>", ""]
    for name, info in cfg.items():
        enabled = bool(info.get("enabled", True))
        status = "включена" if enabled else "выключена"
        lines.append(f"{name}: <b>{status}</b>")
    lines.append("")
    lines.append("Выберите категорию для настройки.")
    kb = _categories_list_keyboard(list(cfg.keys()))
    await message.answer("\n".join(lines), reply_markup=kb)


@router.message(AdminStates.CATEGORIES_SELECT)
async def admin_categories_select(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    cfg = _load_categories_config()
    text = message.text or ""
    if text == "⬅️ Назад в админ-меню":
        level = session.get("level", 1)
        await state.set_state(AdminStates.MAIN)
        await message.answer(
            "🔙 Вы вернулись в главное меню админ-панели.",
            reply_markup=admin_main_keyboard(level),
        )
        return
    if text not in cfg:
        kb = _categories_list_keyboard(list(cfg.keys()))
        await message.answer("Пожалуйста, выберите категорию из списка ниже.", reply_markup=kb)
        return
    await state.update_data(current_category=text)
    info = cfg.get(text, {})
    enabled = bool(info.get("enabled", True))
    disabled_text = info.get("disabled_text") or DEFAULT_CATEGORY_DISABLED_TEXT
    status = "включена" if enabled else "выключена"
    lines = [
        f"Категория: <b>{text}</b>",
        f"Статус: <b>{status}</b>",
        "",
        "Текст при отключении:",
        disabled_text,
    ]
    kb = _category_menu_keyboard(enabled)
    await state.set_state(AdminStates.CATEGORIES_CATEGORY_MENU)
    await message.answer("\n".join(lines), reply_markup=kb)


@router.message(AdminStates.CATEGORIES_CATEGORY_MENU)
async def admin_categories_category_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    data = await state.get_data()
    category = data.get("current_category")
    if not category:
        cfg = _load_categories_config()
        kb = _categories_list_keyboard(list(cfg.keys()))
        await state.set_state(AdminStates.CATEGORIES_SELECT)
        await message.answer("Сначала выберите категорию.", reply_markup=kb)
        return
    cfg = _load_categories_config()
    info = cfg.get(category, {"enabled": True, "disabled_text": DEFAULT_CATEGORY_DISABLED_TEXT})
    enabled = bool(info.get("enabled", True))
    text = message.text or ""
    if text == "⬅️ Назад в админ-меню":
        level = session.get("level", 1)
        await state.set_state(AdminStates.MAIN)
        await message.answer(
            "🔙 Вы вернулись в главное меню админ-панели.",
            reply_markup=admin_main_keyboard(level),
        )
        return
    if text == "🔙 Выбрать другую категорию":
        cfg = _load_categories_config()
        kb = _categories_list_keyboard(list(cfg.keys()))
        await state.set_state(AdminStates.CATEGORIES_SELECT)
        await message.answer("Выберите другую категорию.", reply_markup=kb)
        return
    if text in {"✅ Включить", "⛔ Выключить"}:
        new_enabled = text == "✅ Включить"
        info["enabled"] = new_enabled
        cfg[category] = info
        _save_categories_config(cfg)
        enabled = new_enabled
        status = "включена" if enabled else "выключена"
        disabled_text = info.get("disabled_text") or DEFAULT_CATEGORY_DISABLED_TEXT
        lines = [
            f"Категория: <b>{category}</b>",
            f"Статус: <b>{status}</b>",
            "",
            "Текст при отключении:",
            disabled_text,
        ]
        kb = _category_menu_keyboard(enabled)
        await message.answer("Статус категории обновлён.", reply_markup=kb)
        await message.answer("\n".join(lines), reply_markup=kb)
        return
    if text == "✏️ Текст при отключении":
        await state.set_state(AdminStates.CATEGORY_EDIT_TEXT)
        await message.answer(
            "Отправьте новый текст, который будет показываться при отключённой категории.\n"
            "Для сброса на значение по умолчанию отправьте слово <code>сброс</code>."
        )
        return
    kb = _category_menu_keyboard(enabled)
    await message.answer("Пожалуйста, используйте кнопки меню.", reply_markup=kb)


@router.message(AdminStates.CATEGORY_EDIT_TEXT)
async def admin_category_edit_text(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    data = await state.get_data()
    category = data.get("current_category")
    if not category:
        cfg = _load_categories_config()
        kb = _categories_list_keyboard(list(cfg.keys()))
        await state.set_state(AdminStates.CATEGORIES_SELECT)
        await message.answer("Сначала выберите категорию.", reply_markup=kb)
        return
    cfg = _load_categories_config()
    info = cfg.get(category, {"enabled": True, "disabled_text": DEFAULT_CATEGORY_DISABLED_TEXT})
    text_raw = (message.text or "").strip()
    if text_raw.lower() == "сброс":
        info["disabled_text"] = DEFAULT_CATEGORY_DISABLED_TEXT
    else:
        if not text_raw:
            await message.answer("Текст не может быть пустым. Отправьте новый текст или слово «сброс».")
            return
        info["disabled_text"] = text_raw
    cfg[category] = info
    _save_categories_config(cfg)
    await state.set_state(AdminStates.CATEGORIES_CATEGORY_MENU)
    enabled = bool(info.get("enabled", True))
    status = "включена" if enabled else "выключена"
    disabled_text = info.get("disabled_text") or DEFAULT_CATEGORY_DISABLED_TEXT
    lines = [
        f"Категория: <b>{category}</b>",
        f"Статус: <b>{status}</b>",
        "",
        "Текст при отключении:",
        disabled_text,
    ]
    kb = _category_menu_keyboard(enabled)
    await message.answer("Текст при отключении обновлён.", reply_markup=kb)
    await message.answer("\n".join(lines), reply_markup=kb)


@router.message(AdminStates.MAIN, F.text == "⚙️ Настройки рассылки")
async def admin_mailing_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=1)
    if not session:
        return
    await state.set_state(AdminStates.MAILING_MENU)
    blocklist = _load_broadcast_blocklist()
    ids = blocklist.get("ids", [])
    usernames = blocklist.get("usernames", [])
    lines = [
        "⚙️ <b>Настройки рассылки</b>",
        "",
        "Пользователи в блок-листе не получают массовые рассылки.",
        "",
        f"ID в блок-листе: <b>{len(ids)}</b>",
        f"Usernames в блок-листе: <b>{len(usernames)}</b>",
    ]
    await message.answer("\n".join(lines), reply_markup=admin_mailing_keyboard())


@router.message(AdminStates.MAILING_MENU, F.text == "⬅️ Назад в админ-меню")
async def admin_mailing_back(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=1)
    if not session:
        return
    level = session.get("level", 1)
    await state.set_state(AdminStates.MAIN)
    await message.answer(
        "🔙 Вы вернулись в главное меню админ-панели.",
        reply_markup=admin_main_keyboard(level),
    )


@router.message(AdminStates.MAILING_MENU, F.text == "📋 Показать исключения")
async def admin_mailing_show_list(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=1)
    if not session:
        return
    blocklist = _load_broadcast_blocklist()
    ids = blocklist.get("ids", [])
    usernames = blocklist.get("usernames", [])
    lines = [
        "📋 <b>Исключения из рассылки</b>",
        "",
        "ID:",
    ]
    if ids:
        for v in ids:
            lines.append(f"• <code>{v}</code>")
    else:
        lines.append("• нет")
    lines.append("")
    lines.append("Usernames:")
    if usernames:
        for u in usernames:
            lines.append(f"• @{u}")
    else:
        lines.append("• нет")
    await message.answer("\n".join(lines))


@router.message(AdminStates.MAILING_MENU, F.text == "🚫 Отключить рассылку для ID/@username")
async def admin_mailing_block_start(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=1)
    if not session:
        return
    await state.set_state(AdminStates.MAILING_BLOCK_WAIT_USER)
    await message.answer(
        "Отправьте ID или @username пользователя, которого нужно исключить из рассылок."
    )


@router.message(AdminStates.MAILING_BLOCK_WAIT_USER)
async def admin_mailing_block_process(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=1)
    if not session:
        return
    text_raw = (message.text or "").strip()
    if not text_raw:
        await message.answer("Введите ID или username.")
        return
    ident = text_raw
    blocklist = _load_broadcast_blocklist()
    ids = set(blocklist.get("ids", []))
    usernames = set(blocklist.get("usernames", []))
    if ident.lstrip("@").isdigit():
        ids.add(int(ident.lstrip("@")))
    else:
        usernames.add(ident.lstrip("@").lower())
    _save_broadcast_blocklist({"ids": list(ids), "usernames": list(usernames)})
    await state.set_state(AdminStates.MAILING_MENU)
    await message.answer("Пользователь добавлен в блок-лист рассылок.", reply_markup=admin_mailing_keyboard())


@router.message(AdminStates.MAILING_MENU, F.text == "✅ Включить обратно ID/@username")
async def admin_mailing_unblock_start(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=1)
    if not session:
        return
    await state.set_state(AdminStates.MAILING_UNBLOCK_WAIT_USER)
    await message.answer(
        "Отправьте ID или @username пользователя, которого нужно вернуть в рассылки."
    )


@router.message(AdminStates.MAILING_UNBLOCK_WAIT_USER)
async def admin_mailing_unblock_process(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=1)
    if not session:
        return
    text_raw = (message.text or "").strip()
    if not text_raw:
        await message.answer("Введите ID или username.")
        return
    ident = text_raw
    blocklist = _load_broadcast_blocklist()
    ids = set(blocklist.get("ids", []))
    usernames = set(blocklist.get("usernames", []))
    if ident.lstrip("@").isdigit():
        ids.discard(int(ident.lstrip("@")))
    else:
        usernames.discard(ident.lstrip("@").lower())
    _save_broadcast_blocklist({"ids": list(ids), "usernames": list(usernames)})
    await state.set_state(AdminStates.MAILING_MENU)
    await message.answer("Пользователь удалён из блок-листа рассылок.", reply_markup=admin_mailing_keyboard())


@router.message(Command("logout"))
@router.message(F.text.in_({"⏏️ Выйти из панели", "⬅️ Выйти из админ-панели"}))
async def admin_exit(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    await ctx.db.deactivate_admin_sessions_for_user(message.from_user.id)
    await state.set_state(MenuStates.MAIN)
    await message.bot.set_my_commands(
        get_default_bot_commands(),
        scope=BotCommandScopeChat(chat_id=message.chat.id),
    )
    await message.answer("✅ Вы вышли из админ-панели.", reply_markup=main_menu_keyboard())


@router.message(AdminStates.MAIN)
async def admin_unknown(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    await message.answer(
        "Пожалуйста, используйте кнопки админ-панели внизу.\n"
        "Например, откройте нужный раздел.",
        reply_markup=admin_main_keyboard(session["level"]),
    )


@router.message(
    AdminStates.USER_SYSTEM_MENU,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(
        {
            "👥 Список всех пользователей",
            "🔍 Поиск пользователя",
            "🧑‍💻 Сессии администраторов",
            "⬅️ Назад в админ-меню",
        }
    ),
)
async def admin_unknown_user_system(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    level = session.get("level", 1)
    await message.answer(
        "Пожалуйста, используйте кнопки раздела «Система пользователей».",
        reply_markup=admin_user_system_keyboard(level),
    )


@router.message(
    AdminStates.SCHEDULE_MENU,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(
        {
            "🔄 Перепарсить текущее",
            "🗑 Удалить старые файлы",
            "📋 Просмотреть активные подписки",
            "⬅️ Назад в админ-меню",
        }
    ),
)
async def admin_unknown_schedule_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await message.answer(
        "Пожалуйста, используйте кнопки раздела «Управление расписанием».",
        reply_markup=admin_schedule_keyboard(),
    )


@router.message(
    AdminStates.LOGS_MENU,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(
        {
            "⏱️ Показать uptime",
            "📜 Показать последние N строк логов",
            "🧠 Память и CPU",
            "📥 Скачать весь лог",
            "🧑‍💻 Логи ошибок людей",
            "⬅️ Назад в админ-меню",
        }
    ),
)
async def admin_unknown_logs_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state)
    if not session:
        return
    await message.answer(
        "Пожалуйста, используйте кнопки раздела «Логи и статус».",
        reply_markup=admin_logs_keyboard(),
    )


@router.message(
    AdminStates.BAN_MENU,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(
        {
            "🚫 Бан пользователя",
            "✅ Разбан пользователя",
            "📋 Список забаненных",
            "⬅️ Назад в админ-меню",
        }
    ),
)
async def admin_unknown_ban_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=2)
    if not session:
        return
    await message.answer(
        "Пожалуйста, используйте кнопки раздела «Бан / Разбан».",
        reply_markup=admin_ban_keyboard(),
    )


@router.message(
    AdminStates.MAILING_MENU,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(
        {
            "🚫 Отключить рассылку для ID/@username",
            "✅ Включить обратно ID/@username",
            "📋 Показать исключения",
            "⬅️ Назад в админ-меню",
        }
    ),
)
async def admin_unknown_mailing_menu(message: Message, state: FSMContext) -> None:
    session = await _ensure_admin_session_message(message, state, min_level=1)
    if not session:
        return
    await message.answer(
        "Пожалуйста, используйте кнопки раздела «Настройки рассылки».",
        reply_markup=admin_mailing_keyboard(),
    )


@router.callback_query(F.data.startswith("admin_users_prev:"))
async def admin_users_prev(callback: CallbackQuery, state: FSMContext) -> None:
    session = await _ensure_admin_session_callback(callback, state)
    if not session:
        return
    parts = callback.data.split(":", 1)
    try:
        page = int(parts[1])
    except Exception:
        page = 1
    ctx = get_context()
    per_page = 20
    _, total, pages = await ctx.db.list_users_page(page, per_page)
    if total == 0 or pages == 0:
        await callback.answer("Список пользователей пуст.", show_alert=True)
        return
    prev_page = page - 1 if page > 1 else pages
    users, total, pages = await ctx.db.list_users_page(prev_page, per_page)
    text = _format_users_table(users, start_index=(prev_page - 1) * per_page + 1)
    markup = admin_users_inline_keyboard(prev_page, pages)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users_next:"))
async def admin_users_next(callback: CallbackQuery, state: FSMContext) -> None:
    session = await _ensure_admin_session_callback(callback, state)
    if not session:
        return
    parts = callback.data.split(":", 1)
    try:
        page = int(parts[1])
    except Exception:
        page = 1
    ctx = get_context()
    per_page = 20
    _, total, pages = await ctx.db.list_users_page(page, per_page)
    if total == 0 or pages == 0:
        await callback.answer("Список пользователей пуст.", show_alert=True)
        return
    next_page = page + 1 if page < pages else 1
    users, total, pages = await ctx.db.list_users_page(next_page, per_page)
    text = _format_users_table(users, start_index=(next_page - 1) * per_page + 1)
    markup = admin_users_inline_keyboard(next_page, pages)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users_info:"))
async def admin_users_info(callback: CallbackQuery, state: FSMContext) -> None:
    session = await _ensure_admin_session_callback(callback, state)
    if not session:
        return
    parts = callback.data.split(":", 1)
    try:
        page = int(parts[1])
    except Exception:
        page = 1
    ctx = get_context()
    per_page = 20
    users, total, pages = await ctx.db.list_users_page(page, per_page)
    stats = await ctx.db.get_users_stats()
    if pages == 0:
        pages = 1
    blocked_on_page = sum(1 for u in users if u.get("is_blocked"))
    admins_on_page = sum(1 for u in users if u.get("is_admin"))
    lines = [
        "📊 <b>Статистика пользователей</b>",
        "",
        f"👥 Всего пользователей: <b>{stats['total']}</b>",
        f"🚫 Заблокировали бота: <b>{stats['blocked']}</b>",
        f"🏷 С указанной группой: <b>{stats['with_group']}</b>",
        f"🧑‍💻 Активных админ-сессий: <b>{stats['active_admins']}</b>",
        "",
        f"📄 Страниц всего: <b>{pages}</b>",
        "",
        f"📄 Текущая страница: <b>{page}</b>/<b>{pages}</b>",
        f"👥 На странице: <b>{len(users)}</b>",
        f"🚫 Заблокировано на странице: <b>{blocked_on_page}</b>",
        f"🧑‍💻 Админов на странице: <b>{admins_on_page}</b>",
    ]
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_kill_session:"))
async def admin_kill_session(callback: CallbackQuery, state: FSMContext) -> None:
    session = await _ensure_admin_session_callback(callback, state, min_level=3)
    if not session:
        return
    parts = callback.data.split(":", 1)
    try:
        session_id = int(parts[1])
    except Exception:
        await callback.answer("Некорректный идентификатор сессии.", show_alert=True)
        return
    ctx = get_context()
    target_session = await ctx.db.get_admin_session_by_id(session_id)
    if not target_session or not target_session.get("active"):
        sessions = await ctx.db.get_active_admin_sessions_with_users()
        text = _format_admin_sessions_text(sessions)
        markup = admin_sessions_keyboard(sessions)
        await callback.message.edit_text(text, reply_markup=markup)
        await callback.answer("Сессия уже завершена.", show_alert=True)
        return
    await ctx.db.deactivate_admin_session_by_id(session_id)
    target_tg_id = target_session["tg_id"]
    try:
        await callback.bot.set_my_commands(
            get_default_bot_commands(),
            scope=BotCommandScopeChat(chat_id=target_tg_id),
        )
        ctx_app = get_context()
        storage = getattr(ctx_app, "storage", None)
        if storage is not None:
            key = StorageKey(
                bot_id=callback.bot.id,
                chat_id=target_tg_id,
                user_id=target_tg_id,
                destiny="default",
            )
            remote_state = FSMContext(storage=storage, key=key)
            await remote_state.clear()
            await remote_state.set_state(MenuStates.MAIN)
        await callback.bot.send_message(
            target_tg_id,
            "Ваша сессия администратора была принудительно удалена.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        pass
    sessions = await ctx.db.get_active_admin_sessions_with_users()
    text = _format_admin_sessions_text(sessions)
    markup = admin_sessions_keyboard(sessions)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer("Сессия администратора завершена.", show_alert=True)


@router.callback_query(F.data == "admin_sessions_refresh")
async def admin_sessions_refresh(callback: CallbackQuery, state: FSMContext) -> None:
    session = await _ensure_admin_session_callback(callback, state, min_level=3)
    if not session:
        return
    ctx = get_context()
    sessions = await ctx.db.get_active_admin_sessions_with_users()
    text = _format_admin_sessions_text(sessions)
    markup = admin_sessions_keyboard(sessions)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "broadcast_cancel")
async def admin_broadcast_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    session = await _ensure_admin_session_callback(callback, state, min_level=2)
    if not session:
        return
    level = session.get("level", 1)
    await state.set_state(AdminStates.MAIN)
    await callback.answer("Рассылка отменена.", show_alert=False)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "Рассылка отменена.",
        reply_markup=admin_main_keyboard(level),
    )