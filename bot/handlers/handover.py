"""Обработчик передачи смены — FSM форма + просмотр + приём."""
import logging
from datetime import timezone, timedelta

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.forms import HandoverState
from bot.utils.db_connector import (
    get_user_by_telegram_id,
    save_handover_log,
    get_last_handover,
    accept_handover,
)
from bot.utils.positions import get_position_display
from bot.utils.tg_helpers import safe_edit

router = Router()
logger = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))


def _fmt_dt(dt) -> str:
    if not dt:
        return "—"
    return dt.replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%d.%m %H:%M")


def _handover_menu_keyboard(last_handover=None) -> InlineKeyboardMarkup:
    rows = []
    if last_handover and not last_handover.accepted_by:
        rows.append([InlineKeyboardButton(
            text="✅ Принять смену",
            callback_data=f"handover:accept:{last_handover.handover_id}",
        )])
    rows.append([InlineKeyboardButton(
        text="📝 Написать передачу",
        callback_data="handover:start",
    )])
    rows.append([InlineKeyboardButton(
        text="← Главное меню",
        callback_data="menu:main",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="menu:handover")],
    ])


# ────────────────────────────────────────────────────────────────────────────
#  Меню передачи смены
# ────────────────────────────────────────────────────────────────────────────

async def _build_handover_menu_text(last=None) -> str:
    lines = ["🔄 <b>Передача смены</b>\n"]

    if last:
        importance_label = "🔴 Срочно" if last.importance == "urgent" else "🟢 Обычное"
        accepted_line = (
            f"✅ Принята: {_fmt_dt(last.accepted_at)}"
            if last.accepted_by
            else "⏳ Ещё не принята"
        )
        preview = last.message[:300] + ("…" if len(last.message) > 300 else "")

        lines += [
            "📋 <b>Последняя передача:</b>",
            f"🕐 {_fmt_dt(last.created_at)}  |  {importance_label}",
            f"{accepted_line}\n",
            f"<i>{preview}</i>",
            "",
        ]
    else:
        lines += [
            "<i>Передач ещё не было.</i>",
            "",
            "Сюда заносится информация для следующей смены:\n"
            "• Остатки, проблемы, незавершённые задачи\n"
            "• Особые ситуации с гостями\n"
            "• Технические неисправности",
            "",
        ]

    return "\n".join(lines)


@router.callback_query(F.data == "menu:handover")
async def handover_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    last = await get_last_handover()
    text = await _build_handover_menu_text(last)
    kb = _handover_menu_keyboard(last)
    await safe_edit(callback, text, kb)
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Принять смену
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("handover:accept:"))
async def handover_accept(callback: types.CallbackQuery):
    handover_id = callback.data[len("handover:accept:"):]
    user = await get_user_by_telegram_id(callback.from_user.id)

    ok = await accept_handover(handover_id, callback.from_user.id)
    if not ok:
        await callback.answer("⚠️ Передача не найдена", show_alert=True)
        return

    name = user.full_name if user else callback.from_user.full_name or "Сотрудник"
    pos = get_position_display(user) if user else ""

    await callback.answer("✅ Смена принята!")

    # Обновляем меню — кнопка «Принять» исчезнет
    last = await get_last_handover()
    text = await _build_handover_menu_text(last)
    text += f"\n👤 Принял(а): <b>{name}</b> ({pos})"
    kb = _handover_menu_keyboard(last)
    await safe_edit(callback, text, kb)


# ────────────────────────────────────────────────────────────────────────────
#  Написать передачу — Шаг 1: текст
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "handover:start")
async def handover_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HandoverState.waiting_message)
    text = (
        "📝 <b>Передача смены</b>\n\n"
        "Что нужно знать следующей смене?\n"
        "Напиши сообщение — остатки, проблемы, важные детали.\n\n"
        "<i>Напиши текст ответным сообщением:</i>"
    )
    await safe_edit(callback, text, _cancel_keyboard())
    await callback.answer()


@router.message(HandoverState.waiting_message)
async def handover_message_received(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 3:
        await message.answer(
            "⚠️ Сообщение слишком короткое. Опиши ситуацию подробнее.",
            reply_markup=_cancel_keyboard(),
        )
        return

    await state.update_data(message=message.text.strip())
    await state.set_state(HandoverState.waiting_importance)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Срочно — требует внимания сразу", callback_data="handover:importance:urgent")],
        [InlineKeyboardButton(text="🟢 Обычное — для информации",         callback_data="handover:importance:normal")],
        [InlineKeyboardButton(text="← Назад",                             callback_data="menu:handover")],
    ])
    await message.answer(
        "⚡ <b>Степень важности?</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ────────────────────────────────────────────────────────────────────────────
#  Шаг 2: Важность → Сохранение
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("handover:importance:"), HandoverState.waiting_importance)
async def handover_importance(callback: types.CallbackQuery, state: FSMContext):
    importance = callback.data.split(":")[-1]
    data = await state.get_data()
    message_text = data.get("message", "")

    user = await get_user_by_telegram_id(callback.from_user.id)
    department = (user.department or user.role or "staff") if user else "staff"
    name = user.full_name if user else callback.from_user.full_name or "Сотрудник"
    pos = get_position_display(user) if user else ""
    importance_label = "🔴 Срочно" if importance == "urgent" else "🟢 Обычное"

    try:
        await save_handover_log(
            from_user_id=callback.from_user.id,
            message=message_text,
            from_department=department,
            importance=importance,
        )
        await state.clear()

        # Показываем обновлённое меню сразу после сохранения
        last = await get_last_handover()
        menu_text = await _build_handover_menu_text(last)
        header = (
            f"✅ <b>Передача сохранена!</b>\n"
            f"👤 {name} ({pos})  |  {importance_label}\n\n"
        )
        kb = _handover_menu_keyboard(last)
        await safe_edit(callback, header + menu_text, kb)
        await callback.answer("✅ Сохранено!")

    except Exception as e:
        logger.error(f"Ошибка сохранения передачи: {e}")
        await state.clear()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К передаче смены", callback_data="menu:handover")],
        ])
        await safe_edit(
            callback,
            "⚠️ <b>Не удалось сохранить.</b>\n\nСообщи менеджеру или запиши вручную.",
            kb,
        )
        await callback.answer("⚠️ Ошибка")
