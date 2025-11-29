from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message

from app.core.context import get_context
from app.core.state_utils import preserve_state
from app.core.states import MenuStates, PersonalCabinetStates, HomeworkStates
from app.keyboards.admin import admin_main_keyboard
from app.keyboards.reply import (
    main_menu_keyboard,
    schedule_keyboard,
    personal_cabinet_keyboard,
    personal_settings_keyboard,
)
from app.handlers.admin import _load_categories_config
from app.keyboards.homework import homework_main_keyboard

router = Router()


class SetGroupStates(StatesGroup):
    waiting_for_group = State()


async def _build_personal_cabinet_text(message: Message) -> str:
    ctx = get_context()
    user = await ctx.db.get_user(message.from_user.id)
    group_code = user["group_code"] if user else None
    group_text = group_code if group_code else "не указана"
    premium_until = await ctx.db.get_user_premium_until(message.from_user.id)
    if premium_until:
        premium_str = premium_until.strftime("%d.%m.%Y")
        premium_line = f"Статус премиум: ✅ до {premium_str}"
    else:
        premium_line = "Статус премиум: ❌ нет активной подписки"
    steward_group = await ctx.db.get_steward_group(message.from_user.id)
    if steward_group:
        steward_line = f"Роль: вы являетесь старостой группы {steward_group}"
    else:
        steward_line = None
    notify_enabled = await ctx.db.get_schedule_notify_enabled(message.from_user.id)
    notify_line = (
        "Уведомления об изменении расписания: включены"
        if notify_enabled
        else "Уведомления об изменении расписания: выключены"
    )
    lines: list[str] = [
        "<b>Личный кабинет</b>",
        "",
        f"Ваша группа по умолчанию: <b>{group_text}</b>",
        "",
        premium_line,
        notify_line,
    ]
    if steward_line:
        lines.append(steward_line)
    return "\n".join(lines)


async def _keyboard_for_current_menu(message: Message, state: FSMContext):
    ctx = get_context()
    admin_session = await ctx.db.get_active_admin_session_for_user(message.from_user.id)
    if admin_session:
        return admin_main_keyboard(admin_session["level"])
    current_state = await state.get_state()
    if current_state == MenuStates.SCHEDULE.state:
        return schedule_keyboard()
    if current_state == HomeworkStates.MENU.state:
        return homework_main_keyboard()
    if current_state == PersonalCabinetStates.MENU.state:
        return personal_cabinet_keyboard()
    if current_state == PersonalCabinetStates.SETTINGS.state:
        user = await ctx.db.get_user(message.from_user.id)
        group_code = user["group_code"] if user else None
        has_group = bool(group_code)
        notify_enabled = await ctx.db.get_schedule_notify_enabled(message.from_user.id)
        return personal_settings_keyboard(has_group, notify_enabled)
    return main_menu_keyboard()


async def _keyboard_after_set_group(message: Message, state: FSMContext):
    return await _keyboard_for_current_menu(message, state)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    async with preserve_state(state):
        ctx = get_context()
        admin_session = await ctx.db.get_active_admin_session_for_user(message.from_user.id)
        if admin_session:
            kb = admin_main_keyboard(admin_session["level"])
            text = (
                "<b>НМК Помощник — режим администратора</b>\n\n"
                "Основные команды:\n"
                "/start — вернуться в главное меню\n"
                "/help — эта справка\n"
                "/setmygroup — установить учебную группу по уолчанию\n"
                "/promo — ввести промокод\n"
                "/adminpanel — открыть админ-панель\n"
                "/ai_logs — просмотр логов AI-проверки домашки\n"
                "/givepremium — выдать премиум пользователю\n\n"
                "Главные разделы админ-панели:\n"
                "• «🧩 Система пользователей» — управление пользователями\n"
                "• «📊 Логи и статус» — системные логи и ресурсы\n"
                "• «📅 Управление расписанием» — работа с подписками и файлами расписания\n"
                "• «📢 Рассылка сообщений» и «⚙️ Настройки рассылки» — массовые уведомления\n"
                "• «🚫 Бан / Разбан» — блокировка пользователей\n"
                "• «⚙️ Настройка категорий» — включение/выключение разделов (в том числе Домашка📚)\n\n"
                "Раздел «Домашка📚» в пользовательском меню:\n"
                "• Личная домашка (премиум)\n"
                "• Общая домашка по группе с AI-проверкой и модерацией."
            )
        else:
            kb = await _keyboard_for_current_menu(message, state)
            text = (
                "<b>НМК Помощник</b> — ваш ассистент для учёбы.\n\n"
                "Основные разделы:\n"
                "• «Расписание📋» — расписание на сегодня, завтра и неделю\n"
                "• «Домашка📚» — личные и общие домашние задания\n"
                "• «Личный кабинет👤» — ваша группа по умолчанию и настройки\n\n"
                "Команды:\n"
                "/start — запуск бота и главное меню\n"
                "/help — эта справка\n"
                "/setmygroup — установить учебную группу по умолчанию\n"
                "/promo — ввести промокод (если есть акции)\n\n"
                "Личная домашка доступна премиум-пользователям, общая домашка — всем студентам группы."
            )
        await message.answer(text, reply_markup=kb)
@router.message(Command("promo"))
async def cmd_promo(message: Message, state: FSMContext) -> None:
    async with preserve_state(state):
        kb = await _keyboard_for_current_menu(message, state)
        text = "Сейчас нет активных промоакций. Следите за обновлениями НМК Помощника."
        await message.answer(text, reply_markup=kb)


@router.message(Command("setmygroup"))
async def cmd_setmygroup(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    current_state = await state.get_state()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        raw_group = parts[1].strip()
        if raw_group.endswith("."):
            raw_group = raw_group[:-1].strip()
        canonical = ctx.group_resolver.resolve(raw_group)
        if not canonical:
            await message.answer(
                "Не удалось распознать такую группу. Проверьте написание и попробуйте ещё раз командой /setmygroup."
            )
            return
        await ctx.db.set_user_group(message.from_user.id, canonical)
        kb = await _keyboard_after_set_group(message, state)
        text = (
            f"Группа <b>{canonical}</b> установлена по умолчанию.\n"
            "Вы можете изменить её в любое время, снова вызвав команду /setmygroup."
        )
        await message.answer(text, reply_markup=kb)
        return
    await state.update_data(prev_state=current_state)
    await state.set_state(SetGroupStates.waiting_for_group)
    text = (
        "Отправьте сообщение только с названием вашей учебной группы.\n"
        "Например: <b>ИС-131</b>"
    )
    await message.answer(text)


@router.message(SetGroupStates.waiting_for_group)
async def process_group_input(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    text_raw = message.text or ""
    if text_raw.startswith("/"):
        return
    raw_group = text_raw.strip()
    canonical = ctx.group_resolver.resolve(raw_group)
    if not canonical:
        await message.answer(
            "Не удалось распознать такую группу. Убедитесь, что группа существует и написана корректно, затем отправьте её ещё раз."
        )
        return
    data = await state.get_data()
    prev_state = data.get("prev_state")
    await ctx.db.set_user_group(message.from_user.id, canonical)
    if prev_state:
        await state.set_state(prev_state)
        await state.update_data(prev_state=None)
    else:
        await state.set_state(MenuStates.MAIN)
    kb = await _keyboard_after_set_group(message, state)
    text = (
        f"Группа <b>{canonical}</b> установлена по умолчанию.\n"
        "Вы можете изменить её в любое время, снова вызвав команду /setmygroup."
    )
    await message.answer(text, reply_markup=kb)


@router.message(MenuStates.MAIN, F.text == "Личный кабинет👤")
async def personal_cabinet(message: Message, state: FSMContext) -> None:
    await state.set_state(PersonalCabinetStates.MENU)
    text = await _build_personal_cabinet_text(message)
    await message.answer(text, reply_markup=personal_cabinet_keyboard())


@router.message(PersonalCabinetStates.MENU, F.text == "⬅️ Выйти назад")
async def personal_cabinet_back_to_main(message: Message, state: FSMContext) -> None:
    await state.set_state(MenuStates.MAIN)
    await message.answer("Главное меню НМК Помощника.", reply_markup=main_menu_keyboard())


@router.message(PersonalCabinetStates.MENU, F.text == "Премиум")
async def personal_cabinet_premium(message: Message) -> None:
    text = await _build_personal_cabinet_text(message)
    await message.answer(text, reply_markup=personal_cabinet_keyboard())


@router.message(PersonalCabinetStates.MENU, F.text == "Настройки")
async def personal_cabinet_settings(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    user = await ctx.db.get_user(message.from_user.id)
    group_code = user["group_code"] if user else None
    has_group = bool(group_code)
    notify_enabled = await ctx.db.get_schedule_notify_enabled(message.from_user.id)
    group_text = group_code if group_code else "не указана"
    lines: list[str] = [
        "<b>Настройки личного кабинета</b>",
        "",
        f"Текущая группа по умолчанию: <b>{group_text}</b>",
        "Уведомления об изменении расписания: включены"
        if notify_enabled
        else "Уведомления об изменении расписания: выключены",
    ]
    text = "\n".join(lines)
    await state.set_state(PersonalCabinetStates.SETTINGS)
    await message.answer(text, reply_markup=personal_settings_keyboard(has_group, notify_enabled))


@router.message(PersonalCabinetStates.SETTINGS, F.text == "⬅️ Назад в личный кабинет")
async def personal_settings_back_to_cabinet(message: Message, state: FSMContext) -> None:
    await state.set_state(PersonalCabinetStates.MENU)
    text = await _build_personal_cabinet_text(message)
    await message.answer(text, reply_markup=personal_cabinet_keyboard())


@router.message(PersonalCabinetStates.SETTINGS, F.text.contains("Уведомления о расписании"))
async def personal_settings_toggle_notifications(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    current = await ctx.db.get_schedule_notify_enabled(message.from_user.id)
    new_value = not current
    await ctx.db.set_schedule_notify_enabled(message.from_user.id, new_value)
    user = await ctx.db.get_user(message.from_user.id)
    group_code = user["group_code"] if user else None
    has_group = bool(group_code)
    status_text = "включены" if new_value else "выключены"
    await message.answer(
        f"Уведомления об изменении расписания теперь {status_text}.",
        reply_markup=personal_settings_keyboard(has_group, new_value),
    )


@router.message(
    PersonalCabinetStates.SETTINGS,
    F.text.in_({"Установить группу", "Изменить группу"}),
)
async def personal_settings_set_group_start(message: Message, state: FSMContext) -> None:
    await state.set_state(PersonalCabinetStates.SETTINGS_WAIT_GROUP)
    await message.answer(
        "Отправьте сообщение только с названием вашей учебной группы.\n"
        "Например: <b>ИС-131</b>"
    )


@router.message(PersonalCabinetStates.SETTINGS_WAIT_GROUP)
async def personal_settings_group_input(message: Message, state: FSMContext) -> None:
    if (message.text or "") == "⬅️ Назад в личный кабинет":
        await state.set_state(PersonalCabinetStates.MENU)
        text = await _build_personal_cabinet_text(message)
        await message.answer(text, reply_markup=personal_cabinet_keyboard())
        return
    text_raw = message.text or ""
    if text_raw.startswith("/"):
        return
    ctx = get_context()
    raw_group = text_raw.strip()
    canonical = ctx.group_resolver.resolve(raw_group)
    if not canonical:
        await message.answer(
            "Не удалось распознать такую группу. Убедитесь, что группа существует и написана корректно, затем отправьте её ещё раз."
        )
        return
    await ctx.db.set_user_group(message.from_user.id, canonical)
    notify_enabled = await ctx.db.get_schedule_notify_enabled(message.from_user.id)
    await state.set_state(PersonalCabinetStates.SETTINGS)
    await message.answer(
        f"Группа <b>{canonical}</b> установлена по умолчанию.",
        reply_markup=personal_settings_keyboard(True, notify_enabled),
    )


@router.message(MenuStates.MAIN, F.text == "Расписание📋")
async def schedule_entry(message: Message, state: FSMContext) -> None:
    cfg = _load_categories_config()
    info = cfg.get("Расписание📋", {})
    enabled = bool(info.get("enabled", True))
    if not enabled:
        disabled_text = info.get("disabled_text") or "Функция временно недоступна."
        await message.answer(disabled_text, reply_markup=main_menu_keyboard())
        return
    await state.set_state(MenuStates.SCHEDULE)
    text = "Выберите период, за который показать расписание."
    await message.answer(text, reply_markup=schedule_keyboard())


@router.message(
    MenuStates.MAIN,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_({"Расписание📋", "Домашка📚", "Личный кабинет👤"}),
)
async def unknown_main_menu(message: Message) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопки главного меню внизу.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(
    MenuStates.SCHEDULE,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_({"Сегодня", "Завтра", "На всю неделю", "Выйти назад"}),
)
async def unknown_schedule_menu(message: Message) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопки меню расписания.",
        reply_markup=schedule_keyboard(),
    )