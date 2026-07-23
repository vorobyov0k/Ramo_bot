"""
Регистрация новых пользователей.
"""
import logging

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot import config
from bot.states.forms import RegistrationState
from bot.utils.db_connector import (
    get_user_by_telegram_id,
    create_pending_user,
    approve_user,
    reject_user,
)
from bot.keyboards.inline_buttons import get_registration_buttons
from bot.utils.positions import POSITION_MAP, position_to_role

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """/start — главная точка входа."""
    await state.clear()
    logger.info(f"/start от user_id={message.from_user.id}")

    user = await get_user_by_telegram_id(message.from_user.id)

    if not user:
        await message.answer(
            "👋 <b>Добро пожаловать в RAMO!</b>\n\n"
            "Для доступа к боту нужно пройти регистрацию.\n"
            "Введите ваше <b>ФИО</b>:"
        )
        await state.set_state(RegistrationState.waiting_fio)
        return

    if user.status == "pending":
        await message.answer("⏳ Ваша заявка на рассмотрении. Ожидайте одобрения.")
        return

    if user.status == "rejected":
        await message.answer("❌ Ваша заявка отклонена.")
        return

    if not user.active:
        await message.answer("🔒 Ваш аккаунт деактивирован.")
        return

    from bot.handlers.menu import show_home_screen
    await show_home_screen(message, user)


@router.message(RegistrationState.waiting_fio)
async def process_fio(message: types.Message, state: FSMContext):
    """Шаг 1: Сохраняем ФИО."""
    fio = message.text.strip()
    if len(fio) < 3:
        await message.answer("❌ Слишком короткое имя. Введите полное ФИО:")
        return

    await state.update_data(fio=fio)
    logger.info(f"User {message.from_user.id} ввёл ФИО: {fio}")

    await message.answer(
        f"✅ ФИО: <b>{fio}</b>\n\nВыберите вашу должность:",
        reply_markup=get_registration_buttons()
    )
    await state.set_state(RegistrationState.waiting_role)


@router.callback_query(RegistrationState.waiting_role, F.data.startswith("reg:pos:"))
async def process_role(callback: types.CallbackQuery, state: FSMContext):
    """Шаг 2: Выбор должности."""
    logger.info(f"Callback process_role: data={callback.data}")

    position = callback.data.split(":")[-1]
    await state.update_data(position=position)

    pos_info = POSITION_MAP.get(position)
    position_display = pos_info[0] if pos_info else position

    data = await state.get_data()
    fio = data.get("fio")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="reg:confirm")],
        [InlineKeyboardButton(text="🔄 Выбрать другую должность", callback_data="reg:change_role")],
    ])

    await callback.message.edit_text(
        f"📋 <b>Проверьте данные:</b>\n\n"
        f"ФИО: <b>{fio}</b>\n"
        f"Должность: <b>{position_display}</b>\n\n"
        f"Всё верно?",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationState.waiting_confirm)
    await callback.answer()


@router.callback_query(RegistrationState.waiting_confirm, F.data == "reg:change_role")
async def change_role(callback: types.CallbackQuery, state: FSMContext):
    """Вернуться к выбору должности."""
    logger.info(f"Callback change_role")
    await callback.message.edit_text(
        "Выберите вашу должность:",
        reply_markup=get_registration_buttons()
    )
    await state.set_state(RegistrationState.waiting_role)
    await callback.answer()


@router.callback_query(RegistrationState.waiting_confirm, F.data == "reg:confirm")
async def confirm_registration(callback: types.CallbackQuery, state: FSMContext):
    """Шаг 3: Авто-регистрация и немедленный доступ."""
    logger.info(f"Callback confirm_registration")

    data = await state.get_data()
    fio = data.get("fio")
    position = data.get("position", "barman")

    role = position_to_role(position)

    await create_pending_user(
        telegram_id=callback.from_user.id,
        full_name=fio,
        requested_role=role,
        position=position,
    )
    await approve_user(callback.from_user.id, role=role, position=position)

    from bot.utils.db_connector import get_user_by_telegram_id as _get_user
    from bot.handlers.menu import build_home_screen
    new_user = await _get_user(callback.from_user.id)
    text, keyboard = await build_home_screen(new_user)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    pos_info = POSITION_MAP.get(position)
    position_display = pos_info[0] if pos_info else position
    try:
        await notify_admin(callback.bot, callback.from_user.id, fio, position_display)
    except Exception as e:
        logger.warning(f"Не удалось уведомить админа: {e}")
    await state.clear()
    await callback.answer()


# Fallback — ловит ВСЕ callback с reg: если не попали в handlers выше
@router.callback_query(F.data.startswith("reg:"))
async def fallback_reg(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    logger.warning(f"Fallback reg: data={callback.data}, state={current_state}")
    await callback.answer("⚠️ Сессия устарела. Нажмите /start", show_alert=True)


async def notify_admin(bot, user_id: int, fio: str, role: str):
    """Уведомление админу о новом сотруднике (авто-одобрен)."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin:reject:{user_id}"),
        ],
    ])

    await bot.send_message(
        chat_id=config.ADMIN_TELEGRAM_ID,
        text=(
            f"👤 <b>Новый сотрудник зарегистрировался</b>\n\n"
            f"ФИО: <b>{fio}</b>\n"
            f"Должность: <b>{role}</b>\n"
            f"ID: <code>{user_id}</code>\n\n"
            "Доступ выдан автоматически."
        ),
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("admin:approve:"))
async def admin_approve(callback: types.CallbackQuery):
    """Админ одобряет заявку."""
    if callback.from_user.id != config.ADMIN_TELEGRAM_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[2])
    forced_role = parts[3] if len(parts) > 3 else None

    user = await get_user_by_telegram_id(user_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    role = forced_role or user.requested_role or "barman"
    await approve_user(user_id, role=role)

    await callback.message.edit_text(
        f"✅ <b>Заявка одобрена</b>\n\n"
        f"ФИО: <b>{user.full_name}</b>\n"
        f"Должность: <b>{role}</b>"
    )

    await callback.bot.send_message(
        chat_id=user_id,
        text=f"🎉 <b>Доступ одобрен!</b>\n\nВаша должность: <b>{role}</b>\n\nНажмите /start"
    )
    await callback.answer("✅ Одобрено")


@router.callback_query(F.data.startswith("admin:reject:"))
async def admin_reject(callback: types.CallbackQuery):
    """Админ отклоняет заявку."""
    if callback.from_user.id != config.ADMIN_TELEGRAM_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    user = await get_user_by_telegram_id(user_id)

    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    await reject_user(user_id)

    await callback.message.edit_text(f"❌ <b>Заявка отклонена</b>\n\nФИО: <b>{user.full_name}</b>")
    await callback.bot.send_message(chat_id=user_id, text="❌ <b>Ваша заявка отклонена.</b>")
    await callback.answer("❌ Отклонено")