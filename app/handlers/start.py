from html import escape
import datetime as dt
import json
import traceback
from pathlib import Path

from aiogram import Router, BaseMiddleware
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BotCommandScopeChat

from app.core.commands import get_admin_bot_commands, get_default_bot_commands
from app.core.constants import TOS_URL
from app.core.context import get_context
from app.core.states import MenuStates
from app.keyboards.inline import tos_keyboard
from app.keyboards.reply import main_menu_keyboard

router = Router()

BASE_DIR = Path(__file__).resolve().parents[2]
USER_ERRORS_LOG_PATH = BASE_DIR / "config" / "user_errors.log"
ADMIN_LOGS_USER_ID = 8189336411


def build_tos_message_text(from_user) -> str:
    nickname = escape(from_user.full_name or from_user.username or "друг")
    text = (
        f"Привет, {nickname}!\n\n"
        f"Используя сервис <b>НМК Помощник</b>, вы подтверждаете согласие с "
        f"<a href=\"{TOS_URL}\">условиями пользования</a>.\n\n"
        f"Нажмите «Ок, понятно», чтобы открыть меню."
    )
    return text


class TosMiddleware(BaseMiddleware):
    async def _log_error(self, event, from_user, error: Exception) -> None:
        try:
            user_id = getattr(from_user, "id", None) if from_user else None
            username = getattr(from_user, "username", None) if from_user else None
            chat = getattr(event, "chat", None)
            chat_id = getattr(chat, "id", None) if chat else None
            if isinstance(event, Message):
                payload = event.text or event.caption or ""
            elif isinstance(event, CallbackQuery):
                payload = event.data or ""
            else:
                payload = ""
            tb_text = traceback.format_exc()
            entry = {
                "timestamp": dt.datetime.utcnow().isoformat(),
                "user_id": user_id,
                "chat_id": chat_id,
                "username": username,
                "action": payload,
                "error": str(error),
                "traceback": tb_text,
            }
            USER_ERRORS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with USER_ERRORS_LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            try:
                bot = getattr(event, "bot", None)
                if bot is None and isinstance(event, CallbackQuery):
                    bot = event.message.bot if event.message else None
                if bot is not None:
                    parts = []
                    parts.append("⚠️ Ошибка в боте")
                    parts.append(f"Время (UTC): {entry['timestamp']}")
                    if user_id is not None:
                        parts.append(f"Пользователь: {user_id} @{username}" if username else f"Пользователь: {user_id}")
                    if chat_id is not None:
                        parts.append(f"Чат: {chat_id}")
                    if payload:
                        parts.append(f"Действие: {payload}")
                    parts.append("")
                    parts.append(f"Ошибка: {str(error)}")
                    parts.append("")
                    parts.append("Traceback:")
                    parts.append(tb_text)
                    text = "\n".join(parts)
                    max_len = 4000
                    if len(text) <= max_len:
                        await bot.send_message(ADMIN_LOGS_USER_ID, f"<pre>{escape(text)}</pre>", disable_web_page_preview=True)
                    else:
                        tmp_dir = BASE_DIR / "config" / "tmp_logs"
                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        file_name = f"error_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.log"
                        file_path = tmp_dir / file_name
                        try:
                            with file_path.open("w", encoding="utf-8") as f:
                                f.write(text)
                            from aiogram.types import FSInputFile
                            doc = FSInputFile(str(file_path))
                            await bot.send_document(
                                ADMIN_LOGS_USER_ID,
                                document=doc,
                                caption="⚠️ Ошибка в боте (полный лог).",
                            )
                        finally:
                            try:
                                if file_path.exists():
                                    file_path.unlink()
                            except Exception:
                                pass
            except Exception:
                pass
        except Exception:
            pass

    async def _process(self, handler, event, data, from_user):
        if from_user is None:
            return await handler(event, data)
        ctx = get_context()
        ban_entry = await ctx.db.get_ban_for_user(
            from_user.id,
            getattr(from_user, "username", None),
        )
        if ban_entry:
            reason = ban_entry.get("reason") or "не указана"
            text = (
                "🚫 <b>Доступ к боту ограничен.</b>\n\n"
                "Ваш аккаунт был заблокирован.\n"
                f"Причина блокировки: <b>{escape(str(reason))}</b>\n\n"
                "Если вы считаете, что это ошибка, напишите "
                '<a href="https://t.me/Light_YYagami">администрации</a>.'
            )
            if isinstance(event, Message):
                await event.answer(text, disable_web_page_preview=True)
            elif isinstance(event, CallbackQuery) and event.message:
                await event.message.answer(text, disable_web_page_preview=True)
                await event.answer()
            return
        user = await ctx.db.get_user(from_user.id)
        if user and user.get("tos_accepted"):
            return await handler(event, data)
        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/start"):
                return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "tos_accept":
            return await handler(event, data)
        if not user:
            await ctx.db.ensure_user(
                tg_id=from_user.id,
                username=getattr(from_user, "username", None),
                first_name=getattr(from_user, "first_name", None),
                last_name=getattr(from_user, "last_name", None),
            )
        text = build_tos_message_text(from_user)
        if isinstance(event, Message):
            await event.answer(text, reply_markup=tos_keyboard(), disable_web_page_preview=True)
        elif isinstance(event, CallbackQuery) and event.message:
            await event.message.answer(text, reply_markup=tos_keyboard(), disable_web_page_preview=True)
        return

    async def __call__(self, handler, event, data):
        from_user = getattr(event, "from_user", None)
        try:
            return await self._process(handler, event, data, from_user)
        except Exception as e:
            await self._log_error(event, from_user, e)
            raise


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    ctx = get_context()
    admin_session = await ctx.db.get_active_admin_session_for_user(message.from_user.id)
    if admin_session:
        await message.bot.set_my_commands(
            get_admin_bot_commands(admin_session["level"]),
            scope=BotCommandScopeChat(chat_id=message.chat.id),
        )
    else:
        await message.bot.set_my_commands(
            get_default_bot_commands(),
            scope=BotCommandScopeChat(chat_id=message.chat.id),
        )
    user = await ctx.db.get_user(message.from_user.id)
    if user and user["tos_accepted"]:
        await state.set_state(MenuStates.MAIN)
        text = "Главное меню НМК Помощника."
        await message.answer(text, reply_markup=main_menu_keyboard())
        return
    if not user:
        await ctx.db.ensure_user(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
    text = build_tos_message_text(message.from_user)
    await message.answer(text, reply_markup=tos_keyboard(), disable_web_page_preview=True)


@router.callback_query(lambda c: c.data == "tos_accept")
async def tos_accept(callback: CallbackQuery, state: FSMContext) -> None:
    ctx = get_context()
    await ctx.db.accept_tos(
        tg_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
    )
    await callback.answer()
    await callback.message.edit_text("Согласие с условиями использования получено.")
    await state.set_state(MenuStates.MAIN)
    await callback.message.answer("Главное меню.", reply_markup=main_menu_keyboard())