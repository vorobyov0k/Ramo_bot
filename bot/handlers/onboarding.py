"""
Онбординг новичков — трекер дней 1-30, чек-листы, тест дня 21,
фидбэк ментора, инциденты новичка, фото бара, панель менеджера.
"""
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.forms import (
    OnboardingStartState,
    OnboardingIncidentState,
    OnboardingFeedbackState,
    OnboardingTestState,
    OnboardingShiftPhotoState,
)
from bot.utils.db_connector import (
    get_user_by_telegram_id,
    get_active_workers,
    get_active_onboarding,
    get_onboarding,
    get_all_active_onboardings,
    start_onboarding,
    toggle_onboarding_checklist_item,
    save_onboarding_quiz_result,
    add_onboarding_feedback,
    complete_onboarding,
    save_onboarding_shift_photo,
    get_onboarding_shift_photos,
    save_incident_report,
    get_incidents_for_newcomer,
)
from bot.utils.positions import get_position_display, MANAGER_ROLES
from bot.utils.tg_helpers import safe_edit
from bot.utils.onboarding_content import (
    PHASES,
    KEY_RULES,
    INCIDENT_CATEGORIES,
    QUIZ_QUESTIONS,
    QUIZ_PASS_THRESHOLD,
    get_phase_for_day,
    get_all_item_keys,
    day_number_for as _day_number,
)

router = Router()
logger = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))


def _back_btn(callback_data: str = "menu:main", label: str = "← Главное меню") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=callback_data)


def _item_label_map() -> dict:
    m = {}
    for phase in PHASES:
        for key, label in phase["items"]:
            m[key] = label
    return m


_ITEM_LABELS = _item_label_map()


async def _is_manager(telegram_id: int) -> bool:
    user = await get_user_by_telegram_id(telegram_id)
    return bool(user and user.role in MANAGER_ROLES)


# ────────────────────────────────────────────────────────────────────────────
#  Прогресс новичка (menu:progress)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:progress")
async def my_progress(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    progress = await get_active_onboarding(callback.from_user.id) if user else None

    if not progress:
        text = (
            "📊 <b>Мой прогресс</b>\n\n"
            "Онбординг для тебя пока не запущен.\n"
            "Обратись к менеджеру."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[_back_btn()]])
        await safe_edit(callback, text, kb)
        await callback.answer()
        return

    await _render_progress(callback, progress)


async def _render_progress(callback: types.CallbackQuery, progress):
    day = _day_number(progress)
    phase = get_phase_for_day(min(day, 30))
    mentor = await get_user_by_telegram_id(progress.mentor_id) if progress.mentor_id else None
    done_keys = {i["key"] for i in (progress.checklist_items or []) if i.get("done")}

    lines = [
        f"📊 <b>Мой прогресс — День {day}</b>",
        f"👤 Ментор: <b>{mentor.full_name if mentor else '—'}</b>",
        "",
    ]

    kb_rows = []
    if phase:
        lines.append(f"<b>{phase['title']}</b>")
        for key, label in phase["items"]:
            mark = "✅" if key in done_keys else "⬜"
            lines.append(f"{mark} {label}")
            kb_rows.append([InlineKeyboardButton(
                text=f"{mark} {label[:40]}",
                callback_data=f"onboarding:check:{progress.progress_id}:{key}",
            )])
        lines.append("")

    lines.append("📌 <b>Помни всегда:</b>")
    for rule in KEY_RULES:
        lines.append(f"• {rule}")

    total_done = len(done_keys)
    total_items = len(get_all_item_keys())
    lines.append("")
    lines.append(f"Пройдено пунктов: <b>{total_done}/{total_items}</b>")

    quiz_passed = any(q.get("passed") for q in (progress.quiz_results or []))
    if 21 <= day <= 30 and not quiz_passed:
        kb_rows.append([InlineKeyboardButton(text="📝 Начать тест (день 21)", callback_data=f"onboarding:test:start:{progress.progress_id}")])
    elif quiz_passed:
        lines.append("✅ Тест знаний пройден")

    kb_rows.append([InlineKeyboardButton(text="📸 Фото бара (конец смены)", callback_data="onboarding:photo:start")])
    kb_rows.append([_back_btn()])

    await safe_edit(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await callback.answer()


@router.callback_query(F.data.startswith("onboarding:check:"))
async def toggle_check(callback: types.CallbackQuery):
    _, _, progress_id, key = callback.data.split(":", 3)
    progress = await get_onboarding(progress_id)
    if not progress:
        await callback.answer("⚠️ Не найдено", show_alert=True)
        return
    if callback.from_user.id not in (progress.newcomer_id, progress.mentor_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await toggle_onboarding_checklist_item(progress_id, key)
    progress = await get_onboarding(progress_id)
    await _render_progress(callback, progress)


# ────────────────────────────────────────────────────────────────────────────
#  Тест знаний (день 21)
# ────────────────────────────────────────────────────────────────────────────

def _quiz_question_kb(progress_id: str, q_index: int) -> InlineKeyboardMarkup:
    q = QUIZ_QUESTIONS[q_index]
    rows = [
        [InlineKeyboardButton(text=opt, callback_data=f"onboarding:test:ans:{i}")]
        for i, opt in enumerate(q["options"])
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("onboarding:test:start:"))
async def test_start(callback: types.CallbackQuery, state: FSMContext):
    progress_id = callback.data.split(":")[-1]
    progress = await get_onboarding(progress_id)
    if not progress or callback.from_user.id != progress.newcomer_id:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(OnboardingTestState.in_progress)
    await state.update_data(progress_id=progress_id, q_index=0, answers=[])

    q = QUIZ_QUESTIONS[0]
    await safe_edit(
        callback,
        f"📝 <b>Тест знаний ({1}/{len(QUIZ_QUESTIONS)})</b>\n\n{q['q']}",
        _quiz_question_kb(progress_id, 0),
    )
    await callback.answer()


@router.callback_query(OnboardingTestState.in_progress, F.data.startswith("onboarding:test:ans:"))
async def test_answer(callback: types.CallbackQuery, state: FSMContext):
    chosen = int(callback.data.split(":")[-1])
    data = await state.get_data()
    progress_id = data["progress_id"]
    q_index = data["q_index"]
    answers = list(data["answers"]) + [chosen]

    next_index = q_index + 1
    if next_index < len(QUIZ_QUESTIONS):
        await state.update_data(q_index=next_index, answers=answers)
        q = QUIZ_QUESTIONS[next_index]
        await safe_edit(
            callback,
            f"📝 <b>Тест знаний ({next_index + 1}/{len(QUIZ_QUESTIONS)})</b>\n\n{q['q']}",
            _quiz_question_kb(progress_id, next_index),
        )
        await callback.answer()
        return

    correct = sum(1 for i, a in enumerate(answers) if a == QUIZ_QUESTIONS[i]["correct"])
    score = correct / len(QUIZ_QUESTIONS)
    passed = score >= QUIZ_PASS_THRESHOLD
    await save_onboarding_quiz_result(progress_id, score, passed, answers)
    await state.clear()

    verdict = "✅ ТЕСТ ПРОЙДЕН" if passed else "❌ ТЕСТ НЕ ПРОЙДЕН (нужно ≥80%)"
    text = (
        f"<b>{verdict}</b>\n\n"
        f"Правильных ответов: {correct}/{len(QUIZ_QUESTIONS)} ({score:.0%})"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Мой прогресс", callback_data="menu:progress")],
    ])
    await safe_edit(callback, text, kb)
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Фото бара в конце смены
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "onboarding:photo:start")
async def photo_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OnboardingShiftPhotoState.waiting_photo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[_back_btn("menu:progress", "← Назад")]])
    await safe_edit(callback, "📸 Пришли фото бара ответным сообщением.", kb)
    await callback.answer()


@router.message(OnboardingShiftPhotoState.waiting_photo, F.photo)
async def photo_received(message: types.Message, state: FSMContext):
    progress = await get_active_onboarding(message.from_user.id)
    day = _day_number(progress) if progress else None
    file_id = message.photo[-1].file_id
    await save_onboarding_shift_photo(message.from_user.id, day, file_id)
    await state.clear()
    await message.answer("✅ Фото сохранено. Спасибо!")


@router.message(OnboardingShiftPhotoState.waiting_photo)
async def photo_not_photo(message: types.Message):
    await message.answer("⚠️ Пришли именно фото (не текст).")


# ────────────────────────────────────────────────────────────────────────────
#  Фидбэк ментора
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("onboarding:feedback:start:"))
async def feedback_start(callback: types.CallbackQuery, state: FSMContext):
    progress_id = callback.data.split(":")[-1]
    progress = await get_onboarding(progress_id)
    if not progress or callback.from_user.id != progress.mentor_id:
        await callback.answer("⛔ Только ментор этого новичка может оставить фидбэк", show_alert=True)
        return

    await state.set_state(OnboardingFeedbackState.waiting_text)
    await state.update_data(progress_id=progress_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[_back_btn("onboarding:overview", "← Назад")]])
    await safe_edit(callback, "📝 Напиши фидбэк по новичку (как учится, проблемы, план):", kb)
    await callback.answer()


@router.message(OnboardingFeedbackState.waiting_text)
async def feedback_received(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 3:
        await message.answer("⚠️ Слишком коротко. Опиши подробнее.")
        return
    data = await state.get_data()
    await add_onboarding_feedback(data["progress_id"], message.from_user.id, message.text.strip())
    await state.clear()
    await message.answer("✅ Фидбэк сохранён.")


# ────────────────────────────────────────────────────────────────────────────
#  Инцидент новичка (manager/mentor)
# ────────────────────────────────────────────────────────────────────────────

async def _candidate_newcomers_for(telegram_id: int) -> list:
    """Новички, доступные пользователю для фиксации инцидента: если менеджер — все активные;
    если ментор — только свои подопечные."""
    all_active = await get_all_active_onboardings()
    if await _is_manager(telegram_id):
        return all_active
    return [p for p in all_active if p.mentor_id == telegram_id]


@router.callback_query(F.data == "onboarding:incident:start")
async def incident_start(callback: types.CallbackQuery, state: FSMContext):
    candidates = await _candidate_newcomers_for(callback.from_user.id)
    if not candidates:
        await callback.answer("⛔ Нет доступных новичков", show_alert=True)
        return

    await state.set_state(OnboardingIncidentState.waiting_newcomer)
    rows = []
    for p in candidates:
        user = await get_user_by_telegram_id(p.newcomer_id)
        name = user.full_name if user else str(p.newcomer_id)
        rows.append([InlineKeyboardButton(text=name, callback_data=f"onboarding:incident:nc:{p.progress_id}")])
    rows.append([_back_btn()])
    await safe_edit(callback, "🆘 <b>Инцидент новичка</b>\n\nВыбери новичка:", InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(OnboardingIncidentState.waiting_newcomer, F.data.startswith("onboarding:incident:nc:"))
async def incident_pick_newcomer(callback: types.CallbackQuery, state: FSMContext):
    progress_id = callback.data.split(":")[-1]
    await state.update_data(progress_id=progress_id)
    await state.set_state(OnboardingIncidentState.waiting_category)

    rows = [
        [InlineKeyboardButton(text=f"{label} ({sev})", callback_data=f"onboarding:incident:cat:{key}")]
        for key, (label, sev) in INCIDENT_CATEGORIES.items()
    ]
    rows.append([_back_btn()])
    await safe_edit(callback, "📋 Выбери категорию инцидента:", InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(OnboardingIncidentState.waiting_category, F.data.startswith("onboarding:incident:cat:"))
async def incident_pick_category(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[-1]
    label, severity = INCIDENT_CATEGORIES[key]
    await state.update_data(category=key, category_label=label, severity=severity)
    await state.set_state(OnboardingIncidentState.waiting_description)

    kb = InlineKeyboardMarkup(inline_keyboard=[[_back_btn()]])
    await safe_edit(callback, f"📝 <b>{label}</b>\n\nОпиши, что произошло:", kb)
    await callback.answer()


@router.message(OnboardingIncidentState.waiting_description)
async def incident_description(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 5:
        await message.answer("⚠️ Описание слишком короткое.")
        return

    data = await state.get_data()
    progress = await get_onboarding(data["progress_id"])
    day = _day_number(progress) if progress else None

    incident_id = await save_incident_report(
        incident_type=data["category"],
        reported_by=message.from_user.id,
        description=message.text.strip(),
        datetime_occurred=datetime.utcnow(),
        severity=data["severity"],
        newcomer_id=progress.newcomer_id if progress else None,
        onboarding_day=day,
    )

    await _try_sync_incident_to_sheets(progress, data, message.text.strip(), day)

    await state.clear()
    await message.answer(
        f"✅ <b>Инцидент зафиксирован</b>\n\n"
        f"Категория: {data['category_label']}\n"
        f"Серьёзность: {data['severity']}\n"
        f"ID: <code>{incident_id[:8]}…</code>",
        parse_mode="HTML",
    )


async def _try_sync_incident_to_sheets(progress, data, description, day) -> None:
    try:
        from bot.utils.google_sheets_api import get_sheets_connector
        from bot import config

        if not config.GOOGLE_SHEETS_SPREADSHEET_ID:
            return
        newcomer = await get_user_by_telegram_id(progress.newcomer_id) if progress else None
        sheets = get_sheets_connector()
        sheets.append_row(config.ONBOARDING_SHEET_NAME, [
            datetime.now(MSK).strftime("%d.%m.%Y %H:%M"),
            newcomer.full_name if newcomer else "—",
            get_position_display(newcomer) if newcomer else "—",
            day or "—",
            data["category_label"],
            description,
            data["severity"],
        ])
    except Exception as e:
        logger.warning(f"Онбординг: не удалось синхронизировать инцидент в Google Sheets: {e}")


# ────────────────────────────────────────────────────────────────────────────
#  Панель менеджера — обзор онбордингов
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "onboarding:overview")
async def overview(callback: types.CallbackQuery):
    if not await _is_manager(callback.from_user.id):
        await callback.answer("⛔ Раздел доступен только менеджерам", show_alert=True)
        return

    progresses = await get_all_active_onboardings()
    lines = ["🎓 <b>Онбординг новичков</b>\n"]
    rows = []
    if not progresses:
        lines.append("<i>Активных онбордингов нет.</i>")
    for p in progresses:
        user = await get_user_by_telegram_id(p.newcomer_id)
        name = user.full_name if user else str(p.newcomer_id)
        day = _day_number(p)
        incidents = await get_incidents_for_newcomer(p.newcomer_id)
        lines.append(f"• <b>{name}</b> — день {day}, инцидентов: {len(incidents)}")
        rows.append([InlineKeyboardButton(text=f"👤 {name} (день {day})", callback_data=f"onboarding:view:{p.progress_id}")])

    rows.append([InlineKeyboardButton(text="➕ Начать онбординг", callback_data="onboarding:start:pick")])
    rows.append([InlineKeyboardButton(text="🆘 Инцидент новичка", callback_data="onboarding:incident:start")])
    rows.append([_back_btn("menu:control", "← Панель менеджера")])

    await safe_edit(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("onboarding:view:"))
async def view_newcomer(callback: types.CallbackQuery):
    if not await _is_manager(callback.from_user.id):
        await callback.answer("⛔ Доступно только менеджерам", show_alert=True)
        return

    progress_id = callback.data.split(":")[-1]
    progress = await get_onboarding(progress_id)
    if not progress:
        await callback.answer("⚠️ Не найдено", show_alert=True)
        return

    user = await get_user_by_telegram_id(progress.newcomer_id)
    mentor = await get_user_by_telegram_id(progress.mentor_id) if progress.mentor_id else None
    day = _day_number(progress)
    done = len([i for i in (progress.checklist_items or []) if i.get("done")])
    total = len(get_all_item_keys())
    incidents = await get_incidents_for_newcomer(progress.newcomer_id)
    photos = await get_onboarding_shift_photos(progress.newcomer_id)
    quiz = progress.quiz_results or []
    last_quiz = quiz[-1] if quiz else None
    quiz_line = f"✅ {last_quiz['score']:.0%}" if last_quiz else "— не сдан"
    feedback_log = progress.feedback_log or []

    lines = [
        f"👤 <b>{user.full_name if user else '—'}</b> — день {day}",
        f"Ментор: {mentor.full_name if mentor else '—'}",
        f"Чек-лист: {done}/{total}",
        f"Тест: {quiz_line}",
        f"Инцидентов: {len(incidents)}",
        f"Фото смен: {len(photos)}",
        "",
    ]
    if feedback_log:
        lines.append("<b>Фидбэк ментора (последний):</b>")
        lines.append(feedback_log[-1]["text"])
        lines.append("")

    rows = []
    if progress.mentor_id:
        rows.append([InlineKeyboardButton(text="📝 Оставить фидбэк", callback_data=f"onboarding:feedback:start:{progress.progress_id}")])
    if day >= 21:
        rows.append([
            InlineKeyboardButton(text="✅ Принять", callback_data=f"onboarding:decide:{progress.progress_id}:accepted"),
        ])
        rows.append([
            InlineKeyboardButton(text="🔁 Продлить", callback_data=f"onboarding:decide:{progress.progress_id}:extended"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"onboarding:decide:{progress.progress_id}:rejected"),
        ])
    rows.append([_back_btn("onboarding:overview", "← К списку")])

    await safe_edit(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("onboarding:decide:"))
async def decide(callback: types.CallbackQuery):
    if not await _is_manager(callback.from_user.id):
        await callback.answer("⛔ Доступно только менеджерам", show_alert=True)
        return

    _, _, progress_id, decision = callback.data.split(":")
    progress = await get_onboarding(progress_id)
    if not progress:
        await callback.answer("⚠️ Не найдено", show_alert=True)
        return

    await complete_onboarding(progress_id, decision)

    label = {"accepted": "✅ Принят", "extended": "🔁 Испытание продлено", "rejected": "❌ Отказано"}[decision]
    try:
        await callback.bot.send_message(
            progress.newcomer_id,
            f"📋 <b>Решение по онбордингу:</b> {label}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Онбординг: не удалось уведомить новичка о решении: {e}")

    await callback.answer(f"{label}")
    await overview(callback)


# ────────────────────────────────────────────────────────────────────────────
#  Запуск онбординга нового сотрудника
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "onboarding:start:pick")
async def start_pick_newcomer(callback: types.CallbackQuery, state: FSMContext):
    if not await _is_manager(callback.from_user.id):
        await callback.answer("⛔ Доступно только менеджерам", show_alert=True)
        return

    active = await get_active_workers()
    active_onboarding_ids = {p.newcomer_id for p in await get_all_active_onboardings()}
    candidates = [u for u in active if u.telegram_id not in active_onboarding_ids]

    if not candidates:
        await callback.answer("Нет сотрудников без активного онбординга", show_alert=True)
        return

    await state.set_state(OnboardingStartState.waiting_newcomer)
    rows = [
        [InlineKeyboardButton(text=f"{u.full_name} ({get_position_display(u)})", callback_data=f"onboarding:start:nc:{u.telegram_id}")]
        for u in candidates
    ]
    rows.append([_back_btn("onboarding:overview", "← Назад")])
    await safe_edit(callback, "➕ <b>Начать онбординг</b>\n\nВыбери новичка:", InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(OnboardingStartState.waiting_newcomer, F.data.startswith("onboarding:start:nc:"))
async def start_pick_mentor(callback: types.CallbackQuery, state: FSMContext):
    newcomer_id = int(callback.data.split(":")[-1])
    await state.update_data(newcomer_id=newcomer_id)
    await state.set_state(OnboardingStartState.waiting_mentor)

    active = await get_active_workers()
    mentors = [u for u in active if u.telegram_id != newcomer_id]
    rows = [
        [InlineKeyboardButton(text=f"{u.full_name} ({get_position_display(u)})", callback_data=f"onboarding:start:mt:{u.telegram_id}")]
        for u in mentors
    ]
    rows.append([_back_btn("onboarding:overview", "← Назад")])
    await safe_edit(callback, "👤 Выбери ментора:", InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(OnboardingStartState.waiting_mentor, F.data.startswith("onboarding:start:mt:"))
async def start_finalize(callback: types.CallbackQuery, state: FSMContext):
    mentor_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    newcomer_id = data["newcomer_id"]
    await state.clear()

    await start_onboarding(newcomer_id, mentor_id)

    newcomer = await get_user_by_telegram_id(newcomer_id)
    mentor = await get_user_by_telegram_id(mentor_id)

    for target_id, text in (
        (newcomer_id, f"🎓 <b>Онбординг начат!</b>\n\nТвой ментор: <b>{mentor.full_name if mentor else '—'}</b>\n\nОткрой «📊 Мой прогресс» в главном меню."),
        (mentor_id, f"🎓 <b>Тебе назначен новичок:</b> <b>{newcomer.full_name if newcomer else '—'}</b>"),
    ):
        try:
            await callback.bot.send_message(target_id, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Онбординг: не удалось уведомить {target_id}: {e}")

    await callback.answer("✅ Онбординг запущен")
    await overview(callback)
