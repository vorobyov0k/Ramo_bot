"""
Утилиты для безопасной работы с сообщениями Telegram.

Главная задача — не дать боту «зависнуть»: если callback.message.edit_text
падает с TelegramBadRequest (сообщение является фото/медиа без текста,
либо «message is not modified»), обычный код бросает исключение ДО
callback.answer(), и inline-кнопка навсегда остаётся в состоянии загрузки.
safe_edit это исключает.
"""
import logging

from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def safe_edit(
    callback: types.CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
) -> None:
    """
    Безопасно обновляет экран из callback.

    • Если текст не изменился («message is not modified») — тихо игнорируем.
    • Если текущее сообщение — фото/медиа (нет текста для редактирования)
      или слишком старое — удаляем и отправляем заново.

    ВАЖНО: сама по себе callback.answer() тут НЕ вызывается — это остаётся
    на совести хендлера (чтобы не было двойного ответа). От «вечного спиннера»
    на случай других исключений защищает глобальный error-handler.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        desc = str(e).lower()
        if "message is not modified" in desc:
            return  # контент уже актуален — ничего делать не нужно
        # Фото/медиа-сообщение или сообщение нельзя редактировать — пересоздаём
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
