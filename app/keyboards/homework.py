from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def homework_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📘 Личная домашка"), KeyboardButton(text="📚 Общая домашка")],
            [KeyboardButton(text="⬅️ Назад в главное меню")],
        ],
        resize_keyboard=True,
    )


def homework_personal_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Просмотр личной домашки")],
            [KeyboardButton(text="✏️ Редактор личной домашки")],
            [KeyboardButton(text="⏰ Уведомления о личной домашке")],
            [KeyboardButton(text="⬅️ Назад в меню домашки")],
        ],
        resize_keyboard=True,
    )


def homework_personal_editor_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить личное дз")],
            [KeyboardButton(text="📂 Изменить/удалить личное дз")],
            [KeyboardButton(text="⬅️ Назад в личную домашку")],
        ],
        resize_keyboard=True,
    )


def homework_subjects_keyboard(subjects: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for s in subjects:
        if s:
            rows.append([KeyboardButton(text=str(s))])
    rows.append([KeyboardButton(text="⬅️ Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def homework_edit_action_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Изменить текст"), KeyboardButton(text="🗑 Удалить")],
            [KeyboardButton(text="⬅️ Отмена")],
        ],
        resize_keyboard=True,
    )


def homework_personal_cancel_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить добавление", callback_data="hw_personal_add_cancel")]
        ]
    )


def homework_public_menu_keyboard(is_steward: bool) -> ReplyKeyboardMarkup:
    if is_steward:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📝 Предложить общее дз")],
                [KeyboardButton(text="🔎 Просмотр общего дз")],
                [KeyboardButton(text="👮 Управление ДЗ группы")],
                [KeyboardButton(text="⬅️ Назад в меню домашки")],
            ],
            resize_keyboard=True,
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Предложить общее дз")],
            [KeyboardButton(text="🔎 Просмотр общего дз")],
            [KeyboardButton(text="⬅️ Назад в меню домашки")],
        ],
        resize_keyboard=True,
    )


def homework_public_suggest_cancel_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить отправку", callback_data="hw_public_suggest_cancel")]
        ]
    )


def homework_public_steward_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить общее дз")],
            [KeyboardButton(text="🗑 Удалить общее дз")],
            [KeyboardButton(text="⏳ Очередь предложенных дз")],
            [KeyboardButton(text="🔎 Просмотр общего дз")],
            [KeyboardButton(text="⬅️ Назад в меню домашки")],
        ],
        resize_keyboard=True,
    )


def homework_public_pending_inline(req_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"hw_public_apr:{req_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"hw_public_rej:{req_id}"),
            ]
        ]
    )


def homework_public_manage_inline(hw_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"hw_public_del:{hw_id}")]
        ]
    )