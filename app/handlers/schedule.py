import datetime as dt
from pathlib import Path

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, FSInputFile

from app.core.context import get_context
from app.core.states import MenuStates
from app.keyboards.reply import main_menu_keyboard, schedule_keyboard
from app.services.schedule_service import day_name_ru

router = Router()


class ScheduleGroupStates(StatesGroup):
    WAITING_FOR_GROUP = State()


async def _prepare_day_response(message: Message, group_code: str, target_date: dt.date, title_prefix: str) -> tuple[list[Path], str]:
    ctx = get_context()
    schedule = await ctx.schedule_service.get_schedule_data(group_code, target_date)
    style = await ctx.db.get_schedule_style(message.from_user.id)
    banner = await ctx.schedule_service.generate_day_banner(
        schedule, group_code, target_date, style, title_prefix
    )
    text = ctx.schedule_service.build_day_schedule_text(schedule, group_code, target_date)
    banners = [banner] if banner else []
    return banners, text


async def _prepare_week_response(message: Message, group_code: str, base_date: dt.date) -> tuple[list[Path], str]:
    ctx = get_context()
    schedule = await ctx.schedule_service.get_schedule_data(group_code, base_date)
    style = await ctx.db.get_schedule_style(message.from_user.id)
    banners = await ctx.schedule_service.generate_week_banners(
        schedule, group_code, base_date, style
    )
    text = ctx.schedule_service.build_week_schedule_text(schedule, base_date, group_code)
    return banners, text


async def _send_banners(message: Message, banners: list[Path]) -> None:
    for banner in banners:
        try:
            await message.answer_photo(FSInputFile(banner))
        finally:
            try:
                banner.unlink(missing_ok=True)
            except OSError:
                pass


async def _send_schedule(message: Message, banners: list[Path], text: str) -> None:
    if banners:
        await _send_banners(message, banners)
    await message.answer(text, reply_markup=schedule_keyboard())


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
    banners, text = await _prepare_day_response(message, group_code, today, "Сегодня")
    await _send_schedule(message, banners, text)


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
    banners, text = await _prepare_day_response(message, group_code, tomorrow, "Завтра")
    await _send_schedule(message, banners, text)


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
    banners, text = await _prepare_week_response(message, group_code, today)
    await _send_schedule(message, banners, text)


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
        banners, text = await _prepare_week_response(message, canonical, target_date)
    else:
        prefix = "Сегодня" if offset == 0 else ("Завтра" if offset == 1 else day_name_ru(target_date.weekday()))
        banners, text = await _prepare_day_response(message, canonical, target_date, prefix)
    await state.set_state(MenuStates.SCHEDULE)
    await _send_schedule(message, banners, text)


@router.message(MenuStates.SCHEDULE, F.text == "Выйти назад")
async def schedule_back(message: Message, state: FSMContext) -> None:
    await state.set_state(MenuStates.MAIN)
    text = "Главное меню НМК Помощника."
    await message.answer(text, reply_markup=main_menu_keyboard())