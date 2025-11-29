import datetime as dt

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup

from app.core.context import get_context
from app.core.states import MenuStates, HomeworkStates
from app.keyboards.reply import main_menu_keyboard
from app.keyboards.admin import admin_pending_inline
from app.keyboards.homework import (
    homework_main_keyboard,
    homework_personal_menu_keyboard,
    homework_personal_editor_keyboard,
    homework_personal_cancel_inline,
    homework_public_menu_keyboard,
    homework_public_suggest_cancel_inline,
    homework_subjects_keyboard,
    homework_edit_action_keyboard,
)
from app.handlers.admin import _load_categories_config

router = Router()


async def _is_steward_for_group(message: Message, group_code: str) -> bool:
    ctx = get_context()
    steward_group = await ctx.db.get_steward_group(message.from_user.id)
    if not steward_group:
        return False
    return steward_group.replace(" ", "").replace("-", "").upper() == group_code.replace(" ", "").replace("-", "").upper()


async def _public_menu_keyboard_for_user(message: Message) -> ReplyKeyboardMarkup:
    ctx = get_context()
    user = await ctx.db.get_user(message.from_user.id)
    group_code = user["group_code"] if user else None
    if not group_code:
        return homework_public_menu_keyboard(False)
    is_steward = await _is_steward_for_group(message, group_code)
    return homework_public_menu_keyboard(is_steward)


async def _ensure_group(message: Message) -> str | None:
    ctx = get_context()
    user = await ctx.db.get_user(message.from_user.id)
    group_code = user["group_code"] if user else None
    if not group_code:
        await message.answer(
            "У вас ещё не указана учебная группа.\n\n"
            "Пожалуйста, сначала установите группу командой /setmygroup."
        )
        return None
    return group_code


@router.message(MenuStates.MAIN, F.text == "Домашка📚")
async def homework_entry(message: Message, state: FSMContext) -> None:
    cfg = _load_categories_config()
    info = cfg.get("Домашка📚", {})
    enabled = bool(info.get("enabled", True))
    if not enabled:
        disabled_text = info.get("disabled_text") or "Функция временно недоступна."
        await message.answer(disabled_text, reply_markup=main_menu_keyboard())
        return
    await state.set_state(HomeworkStates.MENU)
    await message.answer(
        "📚 <b>Домашние задания</b>\n\n"
        "Выберите раздел, с которым хотите работать:\n"
        "────────────────────\n"
        "• 📘 <b>Личная домашка</b> — видно только вам\n"
        "• 👥 <b>Общая домашка</b> — для всей вашей группы\n"
        "────────────────────\n"
        "Подсказка: нужные кнопки уже внизу 👇",
        reply_markup=homework_main_keyboard(),
    )


@router.message(HomeworkStates.MENU, F.text == "⬅️ Назад в главное меню")
async def homework_back_to_main(message: Message, state: FSMContext) -> None:
    await state.set_state(MenuStates.MAIN)
    await message.answer("Главное меню НМК Помощника.", reply_markup=main_menu_keyboard())


@router.message(HomeworkStates.MENU, F.text == "📘 Личная домашка")
async def homework_personal_menu(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    group_code = await _ensure_group(message)
    if not group_code:
        return
    is_premium = await ctx.homework_service.is_premium(message.from_user.id)
    if not is_premium:
        await message.answer(
            "⚠️ Личная домашка доступна только премиум-пользователям.\n\n"
            "Обратитесь к администрации, чтобы получить доступ к премиум-функциям.",
            reply_markup=homework_main_keyboard(),
        )
        return
    await state.set_state(HomeworkStates.PERSONAL_MENU)
    await message.answer(
        "<b>Личная домашка</b>\n\n"
        "Сохраняйте и просматривайте задания только для себя.\n"
        "Выберите действие ниже:",
        reply_markup=homework_personal_menu_keyboard(),
    )


@router.message(HomeworkStates.MENU, F.text == "📚 Общая домашка")
async def homework_public_menu(message: Message, state: FSMContext) -> None:
    group_code = await _ensure_group(message)
    if not group_code:
        return
    await state.set_state(HomeworkStates.PUBLIC_MENU)
    kb = await _public_menu_keyboard_for_user(message)
    await message.answer(
        "<b>Общая домашка</b>\n\n"
        "Здесь собраны задания для всей группы. Вы можете предложить новое дз или посмотреть, что уже есть.",
        reply_markup=kb,
    )


@router.message(HomeworkStates.PERSONAL_MENU, F.text == "⬅️ Назад в меню домашки")
async def homework_personal_back_to_hw_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(HomeworkStates.MENU)
    await message.answer(
        "Вы вернулись в меню домашки.",
        reply_markup=homework_main_keyboard(),
    )


@router.message(HomeworkStates.PERSONAL_MENU, F.text == "🔎 Просмотр личной домашки")
async def homework_personal_view(message: Message) -> None:
    ctx = get_context()
    text = await ctx.homework_service.format_personal_view(message.from_user.id)
    await message.answer(text, disable_web_page_preview=True, reply_markup=homework_personal_menu_keyboard())


@router.message(HomeworkStates.PERSONAL_MENU, F.text == "✏️ Редактор личной домашки")
async def homework_personal_editor_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(HomeworkStates.PERSONAL_EDITOR_MENU)
    await message.answer(
        "<b>Редактор личной домашки</b>\n\n"
        "Добавляйте, меняйте или удаляйте личные задания с помощью кнопок ниже.",
        reply_markup=homework_personal_editor_keyboard(),
    )


@router.message(HomeworkStates.PERSONAL_EDITOR_MENU, F.text == "⬅️ Назад в личную домашку")
async def homework_personal_editor_back(message: Message, state: FSMContext) -> None:
    await state.set_state(HomeworkStates.PERSONAL_MENU)
    await message.answer("Вы вернулись в меню личной домашки.", reply_markup=homework_personal_menu_keyboard())


@router.message(HomeworkStates.PERSONAL_EDITOR_MENU, F.text == "➕ Добавить личное дз")
async def homework_personal_add_start(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    group_code = await _ensure_group(message)
    if not group_code:
        return
    subjects = await ctx.schedule_service.get_unique_subjects_for_week(group_code, dt.date.today())
    await state.set_state(HomeworkStates.PERSONAL_ADD_SELECT_PAIR)
    await message.answer(
        "🧩 <b>Добавление личного дз</b>\n\n"
        "Выберите предмет из расписания или напишите название вручную:",
        reply_markup=homework_subjects_keyboard(subjects),
    )


@router.callback_query(F.data == "hw_personal_add_cancel")
async def homework_personal_add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(HomeworkStates.PERSONAL_EDITOR_MENU)
    await callback.answer("Добавление личного дз отменено.")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "Вы вернулись в редактор личной домашки.",
        reply_markup=homework_personal_editor_keyboard(),
    )


@router.message(HomeworkStates.PERSONAL_ADD_SELECT_PAIR)
async def homework_personal_add_pair_name(message: Message, state: FSMContext) -> None:
    if message.text == "⬅️ Отмена":
        await state.set_state(HomeworkStates.PERSONAL_EDITOR_MENU)
        await message.answer("Добавление отменено.", reply_markup=homework_personal_editor_keyboard())
        return
    subject = (message.text or "").strip()
    if not subject or subject.startswith("/"):
        await message.answer("Название пары не может быть пустым. Попробуйте еще раз.")
        return
    await state.update_data(personal_subject=subject)
    await state.set_state(HomeworkStates.PERSONAL_ADD_WAIT_CONTENT)
    await message.answer(
        f"Вы добавляете домашнее задание для пары: <b>{subject}</b>\n\n"
        "Отправьте фото (если нужно) и текст задания.\n"
        "Задание будет автоматически удалено через некоторое время после пары.",
        reply_markup=homework_personal_cancel_inline(),
    )


@router.message(HomeworkStates.PUBLIC_MENU, F.text == "👮 Управление ДЗ группы")
async def homework_public_steward_queue(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    group_code = await _ensure_group(message)
    if not group_code:
        return
    is_steward = await _is_steward_for_group(message, group_code)
    if not is_steward:
        kb = await _public_menu_keyboard_for_user(message)
        await message.answer("Эта функция доступна только старосте своей группы.", reply_markup=kb)
        return
    items, total, pages = ctx.homework_service.load_public_pending_page(1)
    group_items = [item for item in items if item.get("group_code") == group_code]
    if not group_items:
        kb = await _public_menu_keyboard_for_user(message)
        await message.answer("Сейчас нет предложенных заданий для вашей группы.", reply_markup=kb)
        return
    for item in group_items:
        username = item.get("username") or "-"
        subject = item.get("subject") or "-"
        text = item.get("text") or "-"
        ai_raw = item.get("ai_result", {}).get("raw")
        ai_text = ai_raw if ai_raw is not None else "-"
        msg_text = (
            f"Предложил: @{username}\n"
            f"Группа: {group_code}\n"
            f"Предмет: {subject}\n"
            f"Текст:\n{text}\n\n"
            f"AI:\n{ai_text}"
        )
        await message.answer(msg_text, reply_markup=admin_pending_inline(item["id"]))


@router.message(HomeworkStates.PERSONAL_ADD_WAIT_CONTENT, F.photo)
async def homework_personal_add_photos(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    await message.answer("✅ Фото получены, обрабатываю...")
    telegraph_url = await ctx.homework_service.upload_images_and_make_telegraph(message)
    data = await state.get_data()
    data["personal_telegraph_url"] = telegraph_url
    await state.update_data(**data)
    await message.answer(
        "✅ Фотографии обработаны.\nТеперь отправьте одним сообщением текст домашнего задания."
    )


@router.message(HomeworkStates.PERSONAL_ADD_WAIT_CONTENT, F.text)
async def homework_personal_add_text(message: Message, state: FSMContext) -> None:
    if message.text.startswith("/"):
        return
    ctx = get_context()
    data = await state.get_data()
    subject = data.get("personal_subject") or "Без названия"
    telegraph_url = data.get("personal_telegraph_url")
    text = message.text.strip()
    group_code = await _ensure_group(message)
    if not group_code:
        return
    delete_at = await ctx.homework_service.calculate_delete_time(group_code, subject)
    ctx.homework_service.add_personal_homework(
        user_id=message.from_user.id,
        subject=subject,
        text=text,
        telegraph_url=telegraph_url,
        delete_at=delete_at,
    )
    await state.update_data(personal_subject=None, personal_telegraph_url=None)
    await state.set_state(HomeworkStates.PERSONAL_MENU)
    await message.answer(
        "✅ Личное домашнее задание сохранено.",
        reply_markup=homework_personal_menu_keyboard(),
    )


@router.message(HomeworkStates.PERSONAL_EDITOR_MENU, F.text == "📂 Изменить/удалить личное дз")
async def homework_personal_edit_start(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    items = ctx.homework_service._load_personal_hw(message.from_user.id)
    if not items:
        await message.answer(
            "У вас нет активных личных заданий для редактирования.",
            reply_markup=homework_personal_editor_keyboard()
        )
        return
    unique_subjects = sorted(list(set([i.get("subject") for i in items if i.get("subject")])))
    await state.set_state(HomeworkStates.PERSONAL_EDIT_SELECT_SUBJECT)
    await message.answer(
        "Выберите предмет, задание по которому нужно изменить или удалить:",
        reply_markup=homework_subjects_keyboard(unique_subjects)
    )


@router.message(HomeworkStates.PERSONAL_EDIT_SELECT_SUBJECT)
async def homework_personal_edit_subject_select(message: Message, state: FSMContext) -> None:
    if message.text == "⬅️ Отмена":
        await state.set_state(HomeworkStates.PERSONAL_EDITOR_MENU)
        await message.answer("Отменено.", reply_markup=homework_personal_editor_keyboard())
        return
    subject = message.text.strip()
    await state.update_data(edit_subject=subject)
    await state.set_state(HomeworkStates.PERSONAL_EDIT_SELECT_ACTION)
    await message.answer(
        f"Выбрано: <b>{subject}</b>. Что вы хотите сделать?",
        reply_markup=homework_edit_action_keyboard()
    )


@router.message(HomeworkStates.PERSONAL_EDIT_SELECT_ACTION)
async def homework_personal_edit_action_select(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    subject = data.get("edit_subject")
    ctx = get_context()
    if message.text == "🗑 Удалить":
        success = await ctx.homework_service.delete_personal_homework(message.from_user.id, subject)
        if success:
            await message.answer(
                f"✅ Задания по предмету <b>{subject}</b> удалены.",
                reply_markup=homework_personal_editor_keyboard(),
            )
        else:
            await message.answer(
                "Ошибка удаления или задания не найдены.",
                reply_markup=homework_personal_editor_keyboard(),
            )
        await state.set_state(HomeworkStates.PERSONAL_EDITOR_MENU)
    elif message.text == "✏️ Изменить текст":
        await state.set_state(HomeworkStates.PERSONAL_EDIT_WAIT_TEXT)
        await message.answer(
            "Отправьте новый текст для задания (старый будет перезаписан).\n"
            "Фотографии останутся без изменений."
        )
    else:
        await state.set_state(HomeworkStates.PERSONAL_EDITOR_MENU)
        await message.answer("Действие отменено.", reply_markup=homework_personal_editor_keyboard())


@router.message(HomeworkStates.PERSONAL_EDIT_WAIT_TEXT)
async def homework_personal_save_edited_text(message: Message, state: FSMContext) -> None:
    if message.text.startswith("/"):
        return
    data = await state.get_data()
    subject = data.get("edit_subject")
    ctx = get_context()
    items = ctx.homework_service._load_personal_hw(message.from_user.id)
    target_id = None
    for item in items:
        if item.get("subject") == subject:
            target_id = item.get("id")
            break
    if target_id:
        await ctx.homework_service.edit_personal_homework_text(
            message.from_user.id,
            target_id,
            message.text.strip(),
        )
        await message.answer("✅ Текст задания обновлен.", reply_markup=homework_personal_editor_keyboard())
    else:
        await message.answer("❌ Не удалось найти задание для обновления.", reply_markup=homework_personal_editor_keyboard())
    await state.set_state(HomeworkStates.PERSONAL_EDITOR_MENU)


@router.message(HomeworkStates.PERSONAL_MENU, F.text == "⏰ Уведомления о личной домашке")
async def homework_personal_notify_settings(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    current = await ctx.db.get_homework_notify_minutes(message.from_user.id)
    if current is None:
        current = 24 * 60
    await state.set_state(HomeworkStates.PERSONAL_NOTIFICATIONS_MENU)
    await state.update_data(notify_minutes=current)
    hours = current // 60
    await message.answer(
        "<b>Настройки уведомлений о личной домашке</b>\n\n"
        f"Сейчас напоминания приходят примерно за <b>{hours}</b> ч до пары.\n\n"
        "Отправьте число в минутах, за сколько времени до пары присылать уведомление.\n"
        "Например: <code>1440</code> для 24 часов.",
    )


@router.message(HomeworkStates.PERSONAL_NOTIFICATIONS_MENU)
async def homework_personal_notify_set(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Отправьте положительное число минут.")
        return
    minutes = int(text)
    if minutes <= 0:
        await message.answer("Число должно быть больше нуля.")
        return
    await ctx.db.set_homework_notify_minutes(message.from_user.id, minutes)
    hours = minutes // 60
    await state.set_state(HomeworkStates.PERSONAL_MENU)
    await message.answer(
        f"✅ Уведомления будут приходить примерно за <b>{hours}</b> ч до пары.",
        reply_markup=homework_personal_menu_keyboard(),
    )


@router.message(HomeworkStates.PUBLIC_MENU, F.text == "⬅️ Назад в меню домашки")
async def homework_public_back_to_hw_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(HomeworkStates.MENU)
    await message.answer("Вы вернулись в меню домашки.", reply_markup=homework_main_keyboard())


@router.message(HomeworkStates.PUBLIC_MENU, F.text == "🔎 Просмотр общего дз")
async def homework_public_view(message: Message) -> None:
    ctx = get_context()
    group_code = await _ensure_group(message)
    if not group_code:
        return
    text = await ctx.homework_service.format_public_view(group_code)
    kb = await _public_menu_keyboard_for_user(message)
    await message.answer(text, disable_web_page_preview=True, reply_markup=kb)


@router.message(HomeworkStates.PUBLIC_MENU, F.text == "📝 Предложить общее дз")
async def homework_public_suggest_start(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    group_code = await _ensure_group(message)
    if not group_code:
        return
    subjects = await ctx.schedule_service.get_unique_subjects_for_week(group_code, dt.date.today())
    await state.set_state(HomeworkStates.PUBLIC_SUGGEST_WAIT_PAIR)
    await state.update_data(public_group_code=group_code)
    await message.answer(
        "📝 <b>Предложение общего дз</b>\n\n"
        "Выберите предмет из списка или напишите название вручную:",
        reply_markup=homework_subjects_keyboard(subjects),
    )


@router.callback_query(F.data == "hw_public_suggest_cancel")
async def homework_public_suggest_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(HomeworkStates.PUBLIC_MENU)
    await callback.answer("Отправка общего дз отменена.")
    try:
        await callback.message.delete()
    except Exception:
        pass
    kb = await _public_menu_keyboard_for_user(callback.message)
    await callback.message.answer(
        "Вы вернулись в меню общей домашки.",
        reply_markup=kb,
    )


@router.message(HomeworkStates.PUBLIC_SUGGEST_WAIT_PAIR)
async def homework_public_suggest_pair(message: Message, state: FSMContext) -> None:
    if message.text == "⬅️ Отмена":
        await state.set_state(HomeworkStates.PUBLIC_MENU)
        kb = await _public_menu_keyboard_for_user(message)
        await message.answer("Отменено.", reply_markup=kb)
        return
    subject = (message.text or "").strip()
    if not subject or subject.startswith("/"):
        await message.answer("Название пары не может быть пустым. Попробуйте еще раз.")
        return
    await state.update_data(public_subject=subject)
    await state.set_state(HomeworkStates.PUBLIC_SUGGEST_WAIT_CONTENT)
    await message.answer(
        f"Вы предлагаете общее дз для пары: <b>{subject}</b>\n\n"
        "Сначала отправьте фотографии (если нужны), затем текст домашнего задания.",
        reply_markup=homework_public_suggest_cancel_inline(),
    )


@router.message(HomeworkStates.PUBLIC_SUGGEST_WAIT_CONTENT, F.photo)
async def homework_public_suggest_photos(message: Message, state: FSMContext) -> None:
    ctx = get_context()
    await message.answer("✅ Фото получены, обрабатываю...")
    telegraph_url = await ctx.homework_service.upload_images_and_make_telegraph(message)
    data = await state.get_data()
    data["public_telegraph_url"] = telegraph_url
    await state.update_data(**data)
    await message.answer(
        "✅ Фотографии обработаны.\nТеперь отправьте одним сообщением текст домашнего задания."
    )


@router.message(HomeworkStates.PUBLIC_SUGGEST_WAIT_CONTENT, F.text)
async def homework_public_suggest_text(message: Message, state: FSMContext) -> None:
    if message.text.startswith("/"):
        return
    ctx = get_context()
    data = await state.get_data()
    group_code = data.get("public_group_code")
    subject = data.get("public_subject") or "Без названия"
    telegraph_url = data.get("public_telegraph_url")
    text = message.text.strip()
    delete_at = await ctx.homework_service.calculate_delete_time(group_code, subject)
    ai_result = await ctx.homework_service.pollinations_check_homework(text)
    ctx.homework_service.append_ai_log(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        subject=subject,
        text=text,
        telegraph_url=telegraph_url,
        result=ai_result,
    )
    config = ctx.homework_service.load_ai_config()
    auto_accept = config.get("auto_accept", False)
    decision = ai_result.get("decision") or "нет"
    if decision == "да" and auto_accept:
        ctx.homework_service.add_public_homework(
            group_code=group_code,
            subject=subject,
            text=text,
            telegraph_url=telegraph_url,
            delete_at=delete_at,
        )
        await state.update_data(public_group_code=None, public_subject=None, public_telegraph_url=None)
        await state.set_state(HomeworkStates.PUBLIC_MENU)
        kb = await _public_menu_keyboard_for_user(message)
        await message.answer(
            "✅ Домашка прошла автоматическую проверку и добавлена к общей домашке группы.\n\n"
            "Вы можете увидеть её в разделе «🔎 Просмотр общего дз».",
            reply_markup=kb,
        )
        return
    ctx.homework_service.add_public_pending(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        group_code=group_code,
        subject=subject,
        text=text,
        telegraph_url=telegraph_url,
        ai_result=ai_result,
    )
    await state.update_data(public_group_code=None, public_subject=None, public_telegraph_url=None)
    await state.set_state(HomeworkStates.PUBLIC_MENU)
    kb = await _public_menu_keyboard_for_user(message)
    await message.answer(
        "📝 Задание отправлено на проверку старосте или администратору.\n\n"
        "Ожидайте одобрения.",
        reply_markup=kb,
    )