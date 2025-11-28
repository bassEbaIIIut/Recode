from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.core.constants import TOS_URL


def tos_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📃Условия пользования", url=TOS_URL),
            ],
            [
                InlineKeyboardButton(text="Ок, принять✅", callback_data="tos_accept"),
            ],
        ]
    )


def broadcast_cancel_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="broadcast_cancel",
                )
            ]
        ]
    )
