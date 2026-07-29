"""
Фоновый планировщик онбординга.
Ежедневно в 08:30 и 16:00 (МСК) напоминает активным новичкам про стоп-лист,
в 09:30 — про ежедневный бриф. Не шлёт ничего в выходные новичка (шлём всегда,
т.к. график индивидуальный неизвестен планировщику).
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot

from bot.utils.db_connector import (
    get_all_active_onboardings,
    get_user_by_telegram_id,
)
from bot.utils.onboarding_content import day_number_for as _day_number

logger = logging.getLogger(__name__)

MOSCOW_TZ = timezone(timedelta(hours=3))

STOPLIST_TIMES = {"08:30", "16:00"}
BRIEF_TIME = "09:30"

_sent_today: set = set()  # (date_str, time_str)


async def _send_stoplist_reminder(bot: Bot) -> None:
    progresses = await get_all_active_onboardings()
    for progress in progresses:
        day = _day_number(progress)
        if day > 30:
            continue
        try:
            await bot.send_message(
                progress.newcomer_id,
                "⏰ <b>Напоминание: стоп-лист</b>\n\n"
                "Проверь актуальный стоп-лист перед началом смены — "
                "спроси менеджера, если не уверен(а).",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Онбординг: не отправлено напоминание {progress.newcomer_id}: {e}")


async def _send_brief_reminder(bot: Bot) -> None:
    progresses = await get_all_active_onboardings()
    for progress in progresses:
        day = _day_number(progress)
        if day > 30:
            continue
        try:
            await bot.send_message(
                progress.newcomer_id,
                f"🗣 <b>09:30 — Ежедневный бриф</b>\n\n"
                f"День онбординга: <b>{day}</b>\n"
                "Стоп-лист · события дня · задачи · вопросы.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Онбординг: не отправлен бриф {progress.newcomer_id}: {e}")

        if progress.mentor_id:
            mentor = await get_user_by_telegram_id(progress.mentor_id)
            if mentor:
                try:
                    newcomer = await get_user_by_telegram_id(progress.newcomer_id)
                    name = newcomer.full_name if newcomer else str(progress.newcomer_id)
                    await bot.send_message(
                        progress.mentor_id,
                        f"🗣 <b>Бриф по подопечному {name}</b> — день {day}.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"Онбординг: не отправлен бриф ментору {progress.mentor_id}: {e}")


async def scheduler_loop(bot: Bot) -> None:
    """Фоновая задача — каждые 30 секунд проверяет время рассылки онбординга."""
    logger.info("✅ Планировщик онбординга запущен")
    while True:
        try:
            await asyncio.sleep(30)
            now_msk = datetime.now(MOSCOW_TZ)
            date_str = now_msk.strftime("%Y-%m-%d")
            time_str = now_msk.strftime("%H:%M")
            key = (date_str, time_str)

            if key in _sent_today:
                continue

            if time_str in STOPLIST_TIMES:
                _sent_today.add(key)
                logger.info(f"Онбординг: напоминание про стоп-лист ({time_str} МСК)")
                await _send_stoplist_reminder(bot)
            elif time_str == BRIEF_TIME:
                _sent_today.add(key)
                logger.info(f"Онбординг: напоминание про бриф ({time_str} МСК)")
                await _send_brief_reminder(bot)
        except Exception as e:
            logger.error(f"Ошибка планировщика онбординга: {e}")
