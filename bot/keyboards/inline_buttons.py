"""
Inline-кнопки бота RAMO.
Все callback_data формата: action:target:parameter
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Tuple


def get_main_menu_buttons(user_role: str) -> InlineKeyboardMarkup:
    """
    Главное меню, зависит от роли пользователя.
    """
    buttons = [
        [InlineKeyboardButton(text="📚 Библиотека", callback_data="menu:library")],
        [InlineKeyboardButton(text="🎁 Акции",       callback_data="menu:promos")],
        [InlineKeyboardButton(text="📋 Мои задачи", callback_data="menu:tasks")],
    ]

    if user_role in ["barman", "waiter", "security", "admin"]:
        buttons.append([InlineKeyboardButton(text="🚨 Передать информацию", callback_data="menu:handover")])
        buttons.append([InlineKeyboardButton(text="🆘 Инцидент", callback_data="menu:incident")])

    if user_role == "newcomer":
        buttons.append([InlineKeyboardButton(text="📊 Мой прогресс", callback_data="menu:progress")])

    if user_role in ["manager", "admin"]:
        buttons.append([InlineKeyboardButton(text="👥 Контроль команды", callback_data="menu:control")])

    buttons.append([InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_button() -> InlineKeyboardMarkup:
    """Кнопка 'Назад' — возврат на предыдущий уровень."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="nav:back")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])


def get_registration_buttons() -> InlineKeyboardMarkup:
    """Кнопки для выбора должности при регистрации."""
    from bot.utils.positions import REGISTRATION_POSITIONS
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"reg:pos:{slug}")]
        for slug, label in REGISTRATION_POSITIONS
    ])
