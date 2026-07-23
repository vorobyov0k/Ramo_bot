"""
Middleware для проверки авторизации пользователей.
"""
from typing import Callable, Awaitable, Dict, Any, Union

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from bot.utils.db_connector import get_user_by_telegram_id


class AuthMiddleware(BaseMiddleware):
    """
    Проверяет статус пользователя в БД.
    Пропускает:
    - /start (регистрация)
    - Все сообщения, если пользователь в процессе FSM (регистрация, формы)
    - Все callback_query (проверка внутри handler)
    """

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:

        # === ПРОВЕРКА FSM: если пользователь заполняет форму — пропускаем ===
        state = data.get("state")
        if state is not None:
            current_state = await state.get_state()
            if current_state is not None:
                # Пользователь в процессе FSM (регистрация, инцидент и т.д.)
                return await handler(event, data)

        # === CallbackQuery — пропускаем, проверка внутри handler ===
        if isinstance(event, CallbackQuery):
            return await handler(event, data)

        # === Message ===
        if isinstance(event, Message):
            user_id = event.from_user.id
            text = event.text or ""

            # Пропускаем /start
            if text.startswith("/start"):
                return await handler(event, data)

            # Проверяем пользователя в БД
            user = await get_user_by_telegram_id(user_id)

            if not user:
                await event.answer(
                    "👋 Вы не зарегистрированы.\n"
                    "Нажмите /start для регистрации."
                )
                return

            if user.status == "pending":
                await event.answer(
                    "⏳ Ваша заявка на рассмотрении. Ожидайте одобрения."
                )
                return

            if user.status == "rejected":
                await event.answer("❌ Ваша заявка отклонена.")
                return

            if not user.active:
                await event.answer("🔒 Ваш аккаунт деактивирован.")
                return

            # Всё ок — передаём пользователя в handler
            data["user"] = user
            return await handler(event, data)

        # Другие типы событий — пропускаем
        return await handler(event, data)