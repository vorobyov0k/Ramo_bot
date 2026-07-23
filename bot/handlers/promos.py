"""
Раздел «Акции» — просмотр, управление и история оповещений.
Управление доступно ролям: admin, manager, pm.
"""
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.forms import PromoEditState
from bot.utils.db_connector import (
    get_user_by_telegram_id,
    get_all_promos,
    get_promos_for_day,
    toggle_promo,
    update_promo_description,
    get_promo_logs,
)
from bot.utils.promo_scheduler import build_promo_message, MOSCOW_TZ
from bot.utils.tg_helpers import safe_edit
from bot.utils.positions import MANAGER_ROLES

router = Router()
logger = logging.getLogger(__name__)

PROMO_MANAGER_ROLES = MANAGER_ROLES

WEEKDAY_NAMES_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
WEEKDAY_FULL_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье",
}


async def _get_role(user_id: int) -> str:
    user = await get_user_by_telegram_id(user_id)
    return user.role if user else ""


def _is_manager(role: str) -> bool:
    return role in PROMO_MANAGER_ROLES


def _back_btn(target: str = "menu:promos", label: str = "← Назад"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=target)],
    ])


# ─────────────────────────────────────────────────────────────────────────────
#  Просмотр акций — для всех сотрудников
# ─────────────────────────────────────────────────────────────────────────────

async def _promos_text(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    now_msk = datetime.now(MOSCOW_TZ)
    weekday = now_msk.weekday()
    promos = await get_promos_for_day(weekday)

    if promos:
        text = build_promo_message(promos, now_msk)
    else:
        text = "📢 <b>Акции на сегодня:</b>\n\nАкций нет или все отключены."

    role = await _get_role(user_id)
    buttons = []
    if _is_manager(role):
        buttons.append([
            InlineKeyboardButton(text="⚙️ Управление акциями", callback_data="promo:manage"),
            InlineKeyboardButton(text="📋 История",            callback_data="promo:history"),
        ])
    buttons.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])

    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "menu:promos")
async def promos_today(callback: types.CallbackQuery):
    text, kb = await _promos_text(callback.from_user.id)
    await safe_edit(callback, text, kb)
    await callback.answer()


@router.message(F.text.lower().in_({"акции", "акция", "какая сегодня акция?",
                                     "какая акция", "акции сегодня"}))
async def promos_text_command(message: types.Message):
    text, kb = await _promos_text(message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
#  Управление акциями
# ─────────────────────────────────────────────────────────────────────────────

async def _manage_keyboard(promos) -> InlineKeyboardMarkup:
    buttons = []
    for promo in promos:
        status = "✅" if promo.is_active else "❌"
        day_label = ""
        if promo.weekday is not None:
            day_label = f" [{WEEKDAY_NAMES_RU[promo.weekday]}]"
        name = f"{status} {promo.title}{day_label}"
        buttons.append([
            InlineKeyboardButton(text=name, callback_data="noop_promo"),
        ])
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Вкл/Выкл",
                callback_data=f"promo:toggle:{promo.promo_key}",
            ),
            InlineKeyboardButton(
                text="✏️ Описание",
                callback_data=f"promo:edit:{promo.promo_key}",
            ),
        ])
    buttons.append([InlineKeyboardButton(text="← К акциям", callback_data="menu:promos")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "promo:manage")
async def promo_manage(callback: types.CallbackQuery):
    role = await _get_role(callback.from_user.id)
    if not _is_manager(role):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    promos = await get_all_promos()
    kb = await _manage_keyboard(promos)
    await safe_edit(
        callback,
        "⚙️ <b>Управление акциями</b>\n\n"
        "✅ — активна  ❌ — отключена\n"
        "[ПН/ВТ/…] — акция только в этот день\n\n"
        "Нажмите <b>Вкл/Выкл</b> для переключения\n"
        "или <b>Описание</b> для редактирования текста.",
        kb,
    )
    await callback.answer()


@router.callback_query(F.data == "noop_promo")
async def noop_promo(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("promo:toggle:"))
async def promo_toggle(callback: types.CallbackQuery):
    role = await _get_role(callback.from_user.id)
    if not _is_manager(role):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    promo_key = callback.data[len("promo:toggle:"):]
    new_state = await toggle_promo(promo_key)
    if new_state is None:
        await callback.answer("❌ Акция не найдена", show_alert=True)
        return

    status_text = "✅ включена" if new_state else "❌ отключена"
    await callback.answer(f"Акция {status_text}", show_alert=False)

    promos = await get_all_promos()
    kb = await _manage_keyboard(promos)
    await callback.message.edit_reply_markup(reply_markup=kb)


# ─────────────────────────────────────────────────────────────────────────────
#  Редактирование описания акции
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("promo:edit:"))
async def promo_edit_start(callback: types.CallbackQuery, state: FSMContext):
    role = await _get_role(callback.from_user.id)
    if not _is_manager(role):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    promo_key = callback.data[len("promo:edit:"):]
    promos = await get_all_promos()
    promo = next((p for p in promos if p.promo_key == promo_key), None)
    if not promo:
        await callback.answer("❌ Акция не найдена", show_alert=True)
        return

    await state.update_data(promo_key=promo_key)
    await state.set_state(PromoEditState.waiting_description)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖ Отмена", callback_data="promo:manage")],
    ])
    await safe_edit(
        callback,
        f"✏️ <b>Редактирование: {promo.title}</b>\n\n"
        f"Текущее описание:\n<i>{promo.description}</i>\n\n"
        "Введите новое описание:",
        cancel_kb,
    )
    await callback.answer()


@router.message(PromoEditState.waiting_description)
async def promo_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    promo_key = data.get("promo_key")
    await state.clear()

    if not promo_key:
        await message.answer("❌ Ошибка: акция не определена.")
        return

    new_desc = message.text.strip()
    ok = await update_promo_description(promo_key, new_desc, updated_by=message.from_user.id)

    if ok:
        promos = await get_all_promos()
        kb = await _manage_keyboard(promos)
        await message.answer(
            "✅ <b>Описание обновлено.</b>\n\n"
            "⚙️ <b>Управление акциями</b> — выберите действие:",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Не удалось обновить акцию.")


# ─────────────────────────────────────────────────────────────────────────────
#  История оповещений
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "promo:history")
async def promo_history(callback: types.CallbackQuery):
    role = await _get_role(callback.from_user.id)
    if not _is_manager(role):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logs = await get_promo_logs(limit=10)

    if not logs:
        text = "📋 <b>История оповещений</b>\n\nЗаписей пока нет."
    else:
        lines = ["📋 <b>История оповещений (последние 10):</b>\n"]
        msk = timezone(timedelta(hours=3))
        for log in logs:
            sent_msk = log.sent_at.replace(tzinfo=timezone.utc).astimezone(msk)
            date_str = sent_msk.strftime("%d.%m %H:%M")
            preview = log.message_text[:80].replace("\n", " ")
            lines.append(
                f"📅 <b>{date_str}</b> · {log.recipients_count} чел.\n"
                f"<i>{preview}…</i>\n"
            )
        text = "\n".join(lines)

    await safe_edit(callback, text, _back_btn("menu:promos", "← К акциям"))
    await callback.answer()
