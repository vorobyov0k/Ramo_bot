"""
Фоновый планировщик утреннего брифа и напоминания о пересменке.
09:50 — акции + брони + события на сегодня.
15:50 — напоминание о пересменке (10 минут до смены в 16:00): подготовить передачу смены.
Оба — только сотрудникам, у которых сейчас открыта смена.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from aiogram import Bot

from bot.utils.db_connector import (
    get_users_on_shift,
    get_promos_for_day,
    get_upcoming_events,
    PromoConfig,
)

logger = logging.getLogger(__name__)

MOSCOW_TZ = timezone(timedelta(hours=3))

MORNING_BRIEF_TIME = "09:50"
SHIFT_CHANGE_TIME = "15:50"

_EVENT_TYPE_LABELS = {
    "booking": "📅 Бронь",
    "announcement": "📣 Анонс",
    "holiday": "🎉 Праздник",
    "birthday": "🎂 День рождения",
}

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


def build_morning_briefing_message(promos: List[PromoConfig], events: list, now_msk: datetime) -> str:
    weekday = now_msk.weekday()
    day_name = WEEKDAY_NAMES_RU[weekday]
    date_str = f"{now_msk.day} {MONTH_NAMES_RU[now_msk.month]}"

    lines = [f"🌅 <b>Утренний бриф, {date_str} ({day_name}):</b>\n"]

    if promos:
        lines.append("🎁 <b>Акции сегодня:</b>")
        for promo in promos:
            lines.append(f"• <b>{promo.title}</b> — {promo.description}")
        lines.append("")

    if events:
        lines.append("📌 <b>Брони и события:</b>")
        for ev in events:
            label = _EVENT_TYPE_LABELS.get(ev.event_type, ev.event_type)
            ev_msk = ev.event_date.replace(tzinfo=timezone.utc).astimezone(MOSCOW_TZ)
            lines.append(f"• [{label}] {ev.title} — {ev_msk.strftime('%H:%M')}")
        lines.append("")

    return "\n".join(lines).rstrip()


async def do_morning_briefing(bot: Bot) -> None:
    """09:50 — акции + брони + события на сегодня, только сотрудникам на смене."""
    now_msk = datetime.now(MOSCOW_TZ)
    weekday = now_msk.weekday()

    promos = await get_promos_for_day(weekday)
    events = await get_upcoming_events(days=1)

    if not promos and not events:
        logger.info("Утренний бриф: нет акций/событий на сегодня")
        return

    text = build_morning_briefing_message(promos, events, now_msk)
    users = await get_users_on_shift()

    sent = 0
    for user in users:
        try:
            await bot.send_message(user.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.warning(f"Утренний бриф: не отправлено {user.telegram_id}: {e}")

    logger.info(f"Утренний бриф: отправлено {sent} сотрудникам на смене")
    if sent:
        from bot.utils.db_connector import log_action
        await log_action("morning_briefing_sent", details=f"Получателей: {sent}")


# Пересменка реально происходит у официантов; у остальных — редко.
# Чтобы включить бар — добавь "barman"/"bar_manager" в этот набор.
SHIFT_CHANGE_POSITIONS = {"waiter"}


async def do_shift_changeover_reminder(bot: Bot) -> None:
    """15:50 — напоминание о пересменке (10 мин до смены в 16:00), только официантам на смене."""
    text = (
        "🔄 <b>Через 10 минут пересменка (16:00).</b>\n\n"
        "Подготовь передачу смены: остатки, незавершённые задачи, особые ситуации с гостями — "
        "«🔄 Передача смены» в главном меню."
    )
    users = await get_users_on_shift()

    sent = 0
    for user in users:
        if (user.position or "") not in SHIFT_CHANGE_POSITIONS:
            continue
        try:
            await bot.send_message(user.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.warning(f"Напоминание о пересменке: не отправлено {user.telegram_id}: {e}")

    logger.info(f"Напоминание о пересменке: отправлено {sent} официантам на смене")
    if sent:
        from bot.utils.db_connector import log_action
        await log_action("shift_changeover_reminder_sent", details=f"Получателей: {sent}")


async def scheduler_loop(bot: Bot) -> None:
    """Фоновая задача — каждые 30 секунд проверяет время утреннего брифа и пересменки."""
    logger.info("✅ Планировщик брифа и пересменки запущен")
    while True:
        try:
            await asyncio.sleep(30)
            now_msk = datetime.now(MOSCOW_TZ)
            date_str = now_msk.strftime("%Y-%m-%d")
            time_str = now_msk.strftime("%H:%M")

            key = (date_str, time_str)
            if time_str == MORNING_BRIEF_TIME and key not in _sent_today:
                _sent_today.add(key)
                logger.info(f"Планировщик: утренний бриф ({time_str} МСК)")
                await do_morning_briefing(bot)
            elif time_str == SHIFT_CHANGE_TIME and key not in _sent_today:
                _sent_today.add(key)
                logger.info(f"Планировщик: напоминание о пересменке ({time_str} МСК)")
                await do_shift_changeover_reminder(bot)
        except Exception as e:
            logger.error(f"Ошибка планировщика брифа/пересменки: {e}")
