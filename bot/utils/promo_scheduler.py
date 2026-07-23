"""
Фоновый планировщик авто-рассылки акций.
Отправляет сводку актуальных акций всем активным сотрудникам
за 10 минут до начала смены (10:50 и 16:50 по Москве).
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from aiogram import Bot

from bot.utils.db_connector import (
    get_all_users,
    get_promos_for_day,
    log_promo_broadcast,
    PromoConfig,
)

logger = logging.getLogger(__name__)

MOSCOW_TZ = timezone(timedelta(hours=3))

# Времена рассылки (Москва, HH:MM)
BROADCAST_TIMES = {"10:50", "16:50"}

_sent_today: set = set()  # (date_str, time_str)

WEEKDAY_NAMES_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
MONTH_NAMES_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def build_promo_message(promos: List[PromoConfig], now_msk: datetime) -> str:
    weekday = now_msk.weekday()
    day_name = WEEKDAY_NAMES_RU[weekday]
    date_str = f"{now_msk.day} {MONTH_NAMES_RU[now_msk.month]}"

    lines = [f"📢 <b>Акции на сегодня, {date_str} ({day_name}):</b>\n"]

    for promo in promos:
        lines.append(f"<b>{promo.title}</b>")
        lines.append(promo.description)
        lines.append("")

    return "\n".join(lines).rstrip()


async def do_broadcast(bot: Bot) -> None:
    now_msk = datetime.now(MOSCOW_TZ)
    weekday = now_msk.weekday()

    promos = await get_promos_for_day(weekday)
    if not promos:
        logger.info("Авто-рассылка: нет активных акций на сегодня")
        return

    text = build_promo_message(promos, now_msk)
    users = await get_all_users(status="active")

    sent = 0
    for user in users:
        try:
            await bot.send_message(user.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.warning(f"Авто-рассылка: не отправлено {user.telegram_id}: {e}")

    await log_promo_broadcast(text, sent)
    logger.info(f"Авто-рассылка акций: отправлено {sent} сотрудникам")


async def scheduler_loop(bot: Bot) -> None:
    """Фоновая задача — каждые 30 секунд проверяет время рассылки."""
    logger.info("✅ Планировщик акций запущен")
    while True:
        try:
            await asyncio.sleep(30)
            now_msk = datetime.now(MOSCOW_TZ)
            date_str = now_msk.strftime("%Y-%m-%d")
            time_str = now_msk.strftime("%H:%M")

            key = (date_str, time_str)
            if time_str in BROADCAST_TIMES and key not in _sent_today:
                _sent_today.add(key)
                logger.info(f"Планировщик: запуск рассылки ({time_str} МСК)")
                await do_broadcast(bot)
        except Exception as e:
            logger.error(f"Ошибка планировщика акций: {e}")
