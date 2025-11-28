import datetime as dt

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message

from app.core.context import get_context
from app.core.states import MenuStates
from app.keyboards.reply import main_menu_keyboard, schedule_keyboard

router = Router()


class ScheduleGroupStates(StatesGroup):
    WAITING_FOR_GROUP = State()


@router.message(MenuStates.SCHEDULE, F.text == "Сегодня")
async def schedule_today(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    user = await ctx.db.get_user(message.from_user.id)
    group_code = user["group_code"] if user else None
    if not group_code:
        await state.set_state(ScheduleGroupStates.WAITING_FOR_GROUP)
        await state.update_data(schedule_mode="day", schedule_offset=0)
        text = (
            "У вас пока не указана группа по умолчанию.\n"
            "Отправьте название группы, для которой нужно показать расписание на сегодня.\n"
            "Например: <b>ИС-131</b>.\n\n"
            "Если хотите сохранить группу по умолчанию, используйте команду /setmygroup."
        )
        await message.answer(text)
        return
    today = dt.date.today()
    text = await ctx.schedule_service.get_day_schedule_text(group_code, today)
    await message.answer(text, reply_markup=schedule_keyboard())


@router.message(MenuStates.SCHEDULE, F.text == "Завтра")
async def schedule_tomorrow(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    user = await ctx.db.get_user(message.from_user.id)
    group_code = user["group_code"] if user else None
    if not group_code:
        await state.set_state(ScheduleGroupStates.WAITING_FOR_GROUP)
        await state.update_data(schedule_mode="day", schedule_offset=1)
        text = (
            "У вас пока не указана группа по умолчанию.\n"
            "Отправьте название группы, для которой нужно показать расписание на завтра.\n"
            "Например: <b>ИС-131</b>.\n\n"
            "Если хотите сохранить группу по умолчанию, используйте команду /setmygroup."
        )
        await message.answer(text)
        return
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    text = await ctx.schedule_service.get_day_schedule_text(group_code, tomorrow)
    await message.answer(text, reply_markup=schedule_keyboard())


@router.message(MenuStates.SCHEDULE, F.text == "На всю неделю")
async def schedule_week(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    user = await ctx.db.get_user(message.from_user.id)
    group_code = user["group_code"] if user else None
    if not group_code:
        await state.set_state(ScheduleGroupStates.WAITING_FOR_GROUP)
        await state.update_data(schedule_mode="week", schedule_offset=0)
        text = (
            "У вас пока не указана группа по умолчанию.\n"
            "Отправьте название группы, для которой нужно показать расписание на неделю.\n"
            "Например: <b>ИС-131</b>.\n\n"
            "Если хотите сохранить группу по умолчанию, используйте команду /setmygroup."
        )
        await message.answer(text)
        return
    today = dt.date.today()
    text = await ctx.schedule_service.get_week_schedule_text(group_code, today)
    await message.answer(text, reply_markup=schedule_keyboard())


@router.message(ScheduleGroupStates.WAITING_FOR_GROUP)
async def schedule_temp_group_input(message: Message, state: FSMContext) -> None:
    text_raw = message.text or ""
    if text_raw == "Выйти назад":
        await state.set_state(MenuStates.MAIN)
        await message.answer("Главное меню НМК Помощника.", reply_markup=main_menu_keyboard())
        return
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
    data = await state.get_data()
    mode = data.get("schedule_mode") or "day"
    offset = int(data.get("schedule_offset", 0))
    today = dt.date.today()
    target_date = today + dt.timedelta(days=offset)
    if mode == "week":
        text = await ctx.schedule_service.get_week_schedule_text(canonical, target_date)
    else:
        text = await ctx.schedule_service.get_day_schedule_text(canonical, target_date)
    await state.set_state(MenuStates.SCHEDULE)
    await message.answer(text, reply_markup=schedule_keyboard())


@router.message(MenuStates.SCHEDULE, F.text == "Выйти назад")
async def schedule_back(message: Message, state: FSMContext) -> None:
    await state.set_state(MenuStates.MAIN)
    text = "Главное меню НМК Помощника."
    await message.answer(text, reply_markup=main_menu_keyboard())