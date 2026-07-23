"""Обработчик раздела Контроль — панель менеджера."""
import logging
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.utils.db_connector import get_user_by_telegram_id
from bot.utils.positions import MANAGER_ROLES

router = Router()
logger = logging.getLogger(__name__)

_MANAGER_ROLES = MANAGER_ROLES


def _back_btn():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
    ])


@router.callback_query(F.data == "menu:control")
async def control_menu(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    role = user.role if user else None

    if role not in _MANAGER_ROLES:
        await callback.answer("⛔ Раздел доступен только менеджерам", show_alert=True)
        return

    name = user.full_name or "Менеджер"
    text = (
        f"👔 <b>Панель менеджера</b>\n"
        f"Привет, {name}!\n\n"
        "Здесь ты можешь:\n"
        "• Контролировать выполнение чек-листов\n"
        "• Просматривать передачи смен\n"
        "• Следить за инцидентами\n\n"
        "<i>Раздел находится в разработке. "
        "Функции появятся в ближайших обновлениях.</i>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Открыть библиотеку", callback_data="menu:library")],
        [InlineKeyboardButton(text="🆘 Журнал инцидентов", callback_data="menu:incident")],
        [InlineKeyboardButton(text="🔄 Передачи смен", callback_data="menu:handover")],
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
