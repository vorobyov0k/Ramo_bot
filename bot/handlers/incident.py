"""Обработчик инцидентов — FSM форма."""
import logging
from datetime import datetime
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.forms import IncidentState
from bot.utils.db_connector import get_user_by_telegram_id, save_incident_report

router = Router()
logger = logging.getLogger(__name__)

_INCIDENT_TYPES = {
    "spill": "💧 Пролитое на гостя",
    "conflict": "😤 Конфликт с гостем",
    "injury": "🩹 Травма сотрудника",
    "damage": "💥 Повреждение имущества",
    "lost_item": "🔍 Потеря вещи гостя",
    "accident": "⚠️ Прочий инцидент",
}


def _cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="incident:cancel")],
    ])


def _back_btn():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
    ])


# ────────────────────────────────────────────────────────────────────────────
#  Меню инцидентов
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:incident")
async def incident_menu(callback: types.CallbackQuery):
    text = (
        "🆘 <b>Регистрация инцидента</b>\n\n"
        "Здесь ты можешь зафиксировать нештатную ситуацию.\n\n"
        "📌 <b>Когда фиксировать:</b>\n"
        "• Гость пролил напиток / пострадала одежда\n"
        "• Конфликт или жалоба гостя\n"
        "• Травма кого-то из персонала\n"
        "• Повреждение мебели, посуды, оборудования\n"
        "• Гость оставил забытую вещь\n"
        "• Любое ЧП\n\n"
        "<b>Всё фиксируется → менеджер в курсе → решение принято.</b>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Зафиксировать инцидент", callback_data="incident:start")],
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Шаг 1: Выбор типа
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "incident:start")
async def incident_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(IncidentState.waiting_type)

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"incident:type:{key}")]
        for key, label in _INCIDENT_TYPES.items()
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="incident:cancel")])

    await callback.message.edit_text(
        "🆘 <b>Выберите тип инцидента:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("incident:type:"), IncidentState.waiting_type)
async def incident_type_selected(callback: types.CallbackQuery, state: FSMContext):
    incident_type = callback.data[len("incident:type:"):]
    type_label = _INCIDENT_TYPES.get(incident_type, incident_type)

    await state.update_data(incident_type=incident_type, type_label=type_label)
    await state.set_state(IncidentState.waiting_description)

    await callback.message.edit_text(
        f"📝 <b>Инцидент: {type_label}</b>\n\n"
        "Опиши что произошло:\n"
        "• Где случилось?\n"
        "• Что именно произошло?\n"
        "• Кто пострадал / что повреждено?\n"
        "• Как ситуация была урегулирована?\n\n"
        "<i>Напиши в ответном сообщении:</i>",
        reply_markup=_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Шаг 2: Описание → Запрос времени
# ────────────────────────────────────────────────────────────────────────────

@router.message(IncidentState.waiting_description)
async def incident_description_received(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 5:
        await message.answer(
            "⚠️ Описание слишком короткое. Опиши ситуацию подробнее.",
            reply_markup=_cancel_keyboard(),
        )
        return

    await state.update_data(description=message.text.strip())
    await state.set_state(IncidentState.waiting_datetime)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕐 Сейчас", callback_data="incident:time:now")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="incident:cancel")],
    ])
    await message.answer(
        "⏰ <b>Когда произошёл инцидент?</b>\n\n"
        "Нажми <b>«Сейчас»</b> или напиши время в формате:\n"
        "<code>ЧЧ:ММ</code> (например: <code>14:35</code>)",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "incident:time:now", IncidentState.waiting_datetime)
async def incident_time_now(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(datetime_occurred=datetime.utcnow().isoformat())
    await _save_incident(callback, state)


@router.message(IncidentState.waiting_datetime)
async def incident_time_text(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    try:
        today = datetime.now().date()
        parts = text.replace(".", ":").split(":")
        h, m = int(parts[0]), int(parts[1])
        dt = datetime(today.year, today.month, today.day, h, m)
        await state.update_data(datetime_occurred=dt.isoformat())
    except Exception:
        await message.answer(
            "⚠️ Не смог распознать время. Введи в формате <code>ЧЧ:ММ</code>, например <code>14:35</code>",
            parse_mode="HTML",
            reply_markup=_cancel_keyboard(),
        )
        return

    await _save_incident(message, state)


# ────────────────────────────────────────────────────────────────────────────
#  Сохранение инцидента
# ────────────────────────────────────────────────────────────────────────────

async def _save_incident(event, state: FSMContext):
    data = await state.get_data()
    user_id = (
        event.from_user.id
        if isinstance(event, (types.Message, types.CallbackQuery))
        else 0
    )

    dt_str = data.get("datetime_occurred", datetime.utcnow().isoformat())
    try:
        dt = datetime.fromisoformat(dt_str)
    except Exception:
        dt = datetime.utcnow()

    incident_type = data.get("incident_type", "accident")
    type_label = data.get("type_label", "Инцидент")
    description = data.get("description", "—")

    user = await get_user_by_telegram_id(user_id)
    reporter_name = user.full_name if user else "Сотрудник"

    try:
        incident_id = await save_incident_report(
            incident_type=incident_type,
            reported_by=user_id,
            description=description,
            datetime_occurred=dt,
        )

        time_str = dt.strftime("%d.%m.%Y %H:%M")
        preview = description[:200] + ("…" if len(description) > 200 else "")

        text = (
            f"✅ <b>Инцидент зафиксирован!</b>\n\n"
            f"📋 Тип: {type_label}\n"
            f"⏰ Время: {time_str}\n"
            f"👤 Сотрудник: {reporter_name}\n"
            f"🔖 ID: <code>{incident_id[:8]}…</code>\n\n"
            f"📝 <b>Описание:</b>\n<i>{preview}</i>\n\n"
            f"Менеджер смены получит уведомление."
        )
    except Exception as e:
        logger.error(f"Ошибка сохранения инцидента: {e}")
        text = (
            "⚠️ <b>Не удалось сохранить в журнал</b>\n\n"
            "Произошла техническая ошибка. "
            "Немедленно сообщи менеджеру смены устно!"
        )

    await state.clear()

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=_back_btn(), parse_mode="HTML")
        await event.answer("✅ Сохранено!")
    else:
        await event.answer(text, reply_markup=_back_btn(), parse_mode="HTML")


# ────────────────────────────────────────────────────────────────────────────
#  Отмена
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "incident:cancel")
async def incident_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Регистрация инцидента отменена.",
        reply_markup=_back_btn(),
        parse_mode="HTML",
    )
    await callback.answer("Отменено")
