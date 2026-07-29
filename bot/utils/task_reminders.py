"""
Рекомендации по отделам, привязанные ко времени/условиям.
- Бар: 17:00 — сменить плейлист на вечерний.
- Клининг: 10:00-22:00 каждый час — напоминание заполнить журнал гостевой уборной.
- Зал: 10:00-22:00 каждый час — проверка погоды (Open-Meteo, без ключа), рекомендация
  открыть окна при температуре ≥23°C.
- Зал: ручное оповещение (кнопка в admin-панели, для admin/pm/owner) — та же погода,
  но полная логика окна/кондиционер (см. build_climate_message).
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp
from aiogram import Bot

from bot.utils.db_connector import get_users_on_shift

logger = logging.getLogger(__name__)

MOSCOW_TZ = timezone(timedelta(hours=3))

# Воронеж
VORONEZH_LAT = 51.67
VORONEZH_LON = 39.21
WEATHER_URL = (
    f"https://api.open-meteo.com/v1/forecast"
    f"?latitude={VORONEZH_LAT}&longitude={VORONEZH_LON}&current=temperature_2m,precipitation"
)
WINDOW_TEMP_THRESHOLD = 23.0

BAR_PLAYLIST_TIME = "17:00"
HOURLY_TIMES = {f"{h:02d}:00" for h in range(10, 23)}  # 10:00 .. 22:00 включительно

BAR_POSITIONS = {"barman", "bar_manager"}
CLEANING_POSITIONS = {"cleaning"}
FLOOR_POSITIONS = {"waiter", "manager"}

_sent_today: set = set()  # (date_str, time_str, kind)


async def _get_current_temp() -> Optional[float]:
    weather = await get_current_weather()
    return weather[0] if weather else None


async def get_current_weather() -> Optional[tuple[float, float]]:
    """Возвращает (температура °C, осадки мм/ч) или None при ошибке."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(WEATHER_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                current = data.get("current", {})
                temp = current.get("temperature_2m")
                precip = current.get("precipitation")
                if temp is None:
                    return None
                return temp, (precip or 0.0)
    except Exception as e:
        logger.warning(f"Погода: не удалось получить данные: {e}")
        return None


def build_climate_message(temp: float, precipitation: float) -> str:
    """Рекомендация по окнам/кондиционерам на основе температуры и осадков."""
    if temp > WINDOW_TEMP_THRESHOLD and precipitation <= 0:
        return (
            f"☀️ <b>На улице {temp:.0f}°C, без осадков.</b>\n"
            "Откройте окна или включите кондиционеры в зале."
        )
    reason = "дождь" if precipitation > 0 else f"{temp:.0f}°C"
    return (
        f"🌥 <b>На улице {reason}.</b>\n"
        "Закройте окна и включите кондиционеры на 23–24°C."
    )


async def send_manual_climate_notice(bot: Bot) -> tuple[Optional[str], int]:
    """Ручной триггер (кнопка в админке): считает погоду, шлёт зала на смене.
    Возвращает (текст сообщения или None при ошибке погоды, число получателей)."""
    weather = await get_current_weather()
    if weather is None:
        return None, 0
    temp, precip = weather
    text = build_climate_message(temp, precip)

    workers = await get_users_on_shift()
    recipients = [w for w in workers if (w.position or "") in FLOOR_POSITIONS]
    sent = 0
    for w in recipients:
        try:
            await bot.send_message(w.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.warning(f"Оповещение о климате: не отправлено {w.telegram_id}: {e}")
    return text, sent


async def _send_to_positions(bot: Bot, positions: set, text: str) -> None:
    """Шлёт только тем, кто прямо сейчас на смене (ShiftLog открыт) — не всем подключённым к боту."""
    workers = await get_users_on_shift()
    for user in workers:
        if (user.position or "") in positions:
            try:
                await bot.send_message(user.telegram_id, text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Рекомендация отделу: не отправлено {user.telegram_id}: {e}")


async def _check_bar_playlist(bot: Bot) -> None:
    await _send_to_positions(
        bot, BAR_POSITIONS,
        "🎵 <b>17:00 — время сменить плейлист на вечерний.</b>",
    )


async def _check_cleaning_journal(bot: Bot) -> None:
    await _send_to_positions(
        bot, CLEANING_POSITIONS,
        "🧻 <b>Напоминание:</b> заполни журнал гостевой уборной.",
    )


async def _check_windows(bot: Bot) -> None:
    temp = await _get_current_temp()
    if temp is None or temp < WINDOW_TEMP_THRESHOLD:
        return
    await _send_to_positions(
        bot, FLOOR_POSITIONS,
        f"☀️ <b>На улице {temp:.0f}°C — хорошая погода.</b>\n"
        "Можно открыть окна в зале для проветривания.",
    )


async def scheduler_loop(bot: Bot) -> None:
    """Фоновая задача — каждые 30 секунд проверяет время рекомендаций по отделам."""
    logger.info("✅ Планировщик рекомендаций по отделам запущен")
    while True:
        try:
            await asyncio.sleep(30)
            now_msk = datetime.now(MOSCOW_TZ)
            date_str = now_msk.strftime("%Y-%m-%d")
            time_str = now_msk.strftime("%H:%M")

            if time_str == BAR_PLAYLIST_TIME:
                key = (date_str, time_str, "bar_playlist")
                if key not in _sent_today:
                    _sent_today.add(key)
                    logger.info(f"Рекомендации: плейлист бару ({time_str} МСК)")
                    await _check_bar_playlist(bot)

            if time_str in HOURLY_TIMES:
                key_c = (date_str, time_str, "cleaning")
                if key_c not in _sent_today:
                    _sent_today.add(key_c)
                    logger.info(f"Рекомендации: журнал уборной ({time_str} МСК)")
                    await _check_cleaning_journal(bot)

                key_w = (date_str, time_str, "windows")
                if key_w not in _sent_today:
                    _sent_today.add(key_w)
                    await _check_windows(bot)
        except Exception as e:
            logger.error(f"Ошибка планировщика рекомендаций по отделам: {e}")
