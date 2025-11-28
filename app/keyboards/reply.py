from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Расписание📋"),
                KeyboardButton(text="Домашка📚"),
            ],
            [
                KeyboardButton(text="Личный кабинет👤"),
            ],
        ],
        resize_keyboard=True,
    )


def schedule_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Сегодня"),
                KeyboardButton(text="Завтра"),
            ],
            [
                KeyboardButton(text="На всю неделю"),
            ],
            [
                KeyboardButton(text="Выйти назад"),
            ],
        ],
        resize_keyboard=True,
    )


def personal_cabinet_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Премиум")],
            [KeyboardButton(text="Настройки")],
            [KeyboardButton(text="⬅️ Выйти назад")],
        ],
        resize_keyboard=True,
    )


def personal_settings_keyboard(has_group: bool, notify_enabled: bool) -> ReplyKeyboardMarkup:
    group_button = "Изменить группу" if has_group else "Установить группу"
    notify_button = "Уведомления о расписании: Вкл" if notify_enabled else "Уведомления о расписании: Выкл"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=group_button)],
            [KeyboardButton(text=notify_button)],
            [KeyboardButton(text="⬅️ Назад в личный кабинет")],
        ],
        resize_keyboard=True,
    )