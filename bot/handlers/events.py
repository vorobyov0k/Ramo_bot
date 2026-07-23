"""Обработчик раздела События — брони, анонсы, праздники, дни рождения."""
import logging
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot import config
from bot.utils.db_connector import (
    get_user_by_telegram_id,
    get_upcoming_events,
    get_events_by_type,
    create_event,
    delete_event,
)
from bot.states.forms import EventAddBookingState, EventAddAnnouncementState
from bot.utils.positions import MANAGER_ROLES

router = Router()
logger = logging.getLogger(__name__)

# Государственные праздники России (актуальные даты)
_RU_HOLIDAYS = [
    (1, 1,  "🎄 Новый год"),
    (1, 7,  "🎄 Рождество Христово"),
    (2, 23, "💪 День защитника Отечества"),
    (3, 8,  "🌷 Международный женский день"),
    (5, 1,  "🌸 Праздник Весны и Труда"),
    (5, 9,  "🎖 День Победы"),
    (6, 12, "🇷🇺 День России"),
    (11, 4, "🤝 День народного единства"),
]

_EVENT_TYPES = {
    "booking":      "📋 Брони",
    "announcement": "📢 Афиша",
    "holiday":      "🎉 Праздники",
    "birthday":     "🎂 Дни рождения",
}

_MANAGER_ROLES = MANAGER_ROLES


def _back_btn(target: str, label: str = "← Назад"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=target)],
    ])


def _back_row(target: str, label: str = "← Назад"):
    return [InlineKeyboardButton(text=label, callback_data=target)]


# ────────────────────────────────────────────────────────────────────────────
#  Главное меню событий
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:events")
async def events_menu(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    role = user.role if user else None

    buttons = [
        [InlineKeyboardButton(text="📋 Брони на сегодня/завтра", callback_data="events:bookings")],
        [InlineKeyboardButton(text="📢 Афиша мероприятий", callback_data="events:announcements")],
        [InlineKeyboardButton(text="🎉 Праздники & Дни рождения", callback_data="events:holidays_filter")],
    ]
    if role in _MANAGER_ROLES:
        buttons.append([
            InlineKeyboardButton(text="➕ Добавить бронь", callback_data="events:add_booking"),
            InlineKeyboardButton(text="📣 Добавить анонс", callback_data="events:add_announcement"),
        ])
    buttons.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])

    text = "📅 <b>События RAMO</b>\n\nВыберите раздел:"
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Брони
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "events:bookings")
async def events_bookings(callback: types.CallbackQuery):
    events = await get_upcoming_events(event_type="booking", days=2)

    if not events:
        text = (
            "📋 <b>Брони на сегодня и завтра</b>\n\n"
            "<i>Бронирований не найдено.</i>\n\n"
            "Добавить бронь может менеджер/администратор."
        )
    else:
        now = datetime.utcnow()
        today_str = now.strftime("%d.%m")
        tomorrow_str = (now + timedelta(days=1)).strftime("%d.%m")

        lines = ["📋 <b>Брони на сегодня и завтра</b>\n"]
        for e in events:
            dt = e.event_date
            date_label = dt.strftime("%d.%m")
            time_str = dt.strftime("%H:%M")
            meta = e.meta or {}
            guests = meta.get("guest_count", "?")
            phone = meta.get("phone", "")
            comment = meta.get("comment", "")

            if date_label == today_str:
                prefix = "🟢 Сегодня"
            elif date_label == tomorrow_str:
                prefix = "🔵 Завтра"
            else:
                prefix = f"📅 {date_label}"

            lines.append(f"{prefix} <b>{time_str}</b> — {e.title}")
            lines.append(f"   👥 Гостей: {guests}  |  📞 {phone}")
            if comment:
                lines.append(f"   💬 {comment}")
            lines.append("")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n..."

    await callback.message.edit_text(
        text,
        reply_markup=_back_btn("menu:events", "← К событиям"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Афиша
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "events:announcements")
async def events_announcements(callback: types.CallbackQuery):
    events = await get_upcoming_events(event_type="announcement", days=60)

    if not events:
        text = (
            "📢 <b>Афиша мероприятий</b>\n\n"
            "<i>Анонсов не найдено.</i>\n\n"
            "Добавить анонс может менеджер/администратор."
        )
    else:
        lines = ["📢 <b>Афиша RAMO</b>\n"]
        for e in events:
            date_str = e.event_date.strftime("%d.%m.%Y %H:%M")
            lines.append(f"📅 <b>{date_str}</b> — {e.title}")
            if e.description:
                lines.append(f"   {e.description}")
            lines.append("")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n..."

    await callback.message.edit_text(
        text,
        reply_markup=_back_btn("menu:events", "← К событиям"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Праздники & Дни рождения — выбор периода
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "events:holidays_filter")
async def holidays_filter(callback: types.CallbackQuery):
    """Меню выбора периода для праздников и дней рождения."""
    text = "🎉 <b>Праздники & Дни рождения</b>\n\nВыберите период:"
    buttons = [
        [InlineKeyboardButton(text="🟢 Сегодня", callback_data="events:hol_today")],
        [InlineKeyboardButton(text="🔵 Завтра", callback_data="events:hol_tomorrow")],
        [InlineKeyboardButton(text="📅 На неделю", callback_data="events:hol_week")],
        [InlineKeyboardButton(text="📆 На месяц", callback_data="events:hol_month")],
        _back_row("menu:events", "← К событиям"),
    ]
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "events:hol_today")
async def holidays_today(callback: types.CallbackQuery):
    """Праздники и дни рождения на сегодня."""
    now = datetime.utcnow()
    today_str = now.strftime("%d.%m")

    # Праздники на сегодня
    today_holidays = [(m, d, name) for m, d, name in _RU_HOLIDAYS
                      if f"{d:02d}.{m:02d}" == today_str]

    # Дни рождения на сегодня
    birthdays = await get_upcoming_events(event_type="birthday", days=365)
    today_birthdays = [e for e in birthdays if e.event_date.strftime("%d.%m") == today_str]

    lines = [f"🟢 <b>Сегодня, {today_str}</b>\n"]

    if not today_holidays and not today_birthdays:
        lines.append("<i>Праздники и дни рождения не найдены.</i>")
    else:
        if today_holidays:
            lines.append("<b>🎉 Праздники:</b>")
            for m, d, name in today_holidays:
                lines.append(f"  • {name}")
            lines.append("")

        if today_birthdays:
            lines.append("<b>🎂 Дни рождения:</b>")
            for e in today_birthdays:
                lines.append(f"  • {e.title}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_btn("events:holidays_filter", "← Выбрать период"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "events:hol_tomorrow")
async def holidays_tomorrow(callback: types.CallbackQuery):
    """Праздники и дни рождения на завтра."""
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%d.%m")

    # Праздники на завтра
    tomorrow_holidays = [(m, d, name) for m, d, name in _RU_HOLIDAYS
                         if f"{d:02d}.{m:02d}" == tomorrow_str]

    # Дни рождения на завтра
    birthdays = await get_upcoming_events(event_type="birthday", days=365)
    tomorrow_birthdays = [e for e in birthdays if e.event_date.strftime("%d.%m") == tomorrow_str]

    lines = [f"🔵 <b>Завтра, {tomorrow_str}</b>\n"]

    if not tomorrow_holidays and not tomorrow_birthdays:
        lines.append("<i>Праздники и дни рождения не найдены.</i>")
    else:
        if tomorrow_holidays:
            lines.append("<b>🎉 Праздники:</b>")
            for m, d, name in tomorrow_holidays:
                lines.append(f"  • {name}")
            lines.append("")

        if tomorrow_birthdays:
            lines.append("<b>🎂 Дни рождения:</b>")
            for e in tomorrow_birthdays:
                lines.append(f"  • {e.title}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_btn("events:holidays_filter", "← Выбрать период"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "events:hol_week")
async def holidays_week(callback: types.CallbackQuery):
    """Праздники и дни рождения на неделю."""
    now = datetime.utcnow()
    week_end = now + timedelta(days=7)

    lines = [f"📅 <b>На неделю ({now.strftime('%d.%m')} — {week_end.strftime('%d.%m')})</b>\n"]

    # Праздники на неделю
    week_holidays = []
    for m, d, name in _RU_HOLIDAYS:
        try:
            hdate = datetime(now.year, m, d)
            if hdate < now:
                hdate = datetime(now.year + 1, m, d)
            if now <= hdate <= week_end:
                week_holidays.append((hdate, name))
        except ValueError:
            continue

    # Дни рождения на неделю
    birthdays = await get_upcoming_events(event_type="birthday", days=365)
    week_birthdays = [e for e in birthdays if now <= e.event_date <= week_end]

    if not week_holidays and not week_birthdays:
        lines.append("<i>Праздники и дни рождения не найдены.</i>")
    else:
        all_events = []

        for hdate, name in week_holidays:
            all_events.append((hdate, f"🎉 {name}"))

        for e in week_birthdays:
            all_events.append((e.event_date, f"🎂 {e.title}"))

        all_events.sort()

        for edate, desc in all_events:
            lines.append(f"  {edate.strftime('%a, %d.%m')} — {desc}".replace("Mon", "Пн").replace("Tue", "Вт").replace("Wed", "Ср").replace("Thu", "Чт").replace("Fri", "Пт").replace("Sat", "Сб").replace("Sun", "Вс"))

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_btn("events:holidays_filter", "← Выбрать период"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "events:hol_month")
async def holidays_month(callback: types.CallbackQuery):
    """Праздники и дни рождения на месяц."""
    now = datetime.utcnow()
    month_end = now + timedelta(days=30)

    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
    }

    lines = [f"📆 <b>На месяц ({now.strftime('%d.%m')} — {month_end.strftime('%d.%m')})</b>\n"]

    # Праздники на месяц
    month_holidays = []
    for m, d, name in _RU_HOLIDAYS:
        try:
            hdate = datetime(now.year, m, d)
            if hdate < now:
                hdate = datetime(now.year + 1, m, d)
            if now <= hdate <= month_end:
                month_holidays.append((hdate, name))
        except ValueError:
            continue

    # Дни рождения на месяц
    birthdays = await get_upcoming_events(event_type="birthday", days=365)
    month_birthdays = [e for e in birthdays if now <= e.event_date <= month_end]

    if not month_holidays and not month_birthdays:
        lines.append("<i>Праздники и дни рождения не найдены.</i>")
    else:
        all_events = []

        for hdate, name in month_holidays:
            all_events.append((hdate, f"🎉 {name}"))

        for e in month_birthdays:
            all_events.append((e.event_date, f"🎂 {e.title}"))

        all_events.sort()

        for edate, desc in all_events:
            lines.append(f"  {edate.strftime('%d.%m')} — {desc}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_btn("events:holidays_filter", "← Выбрать период"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Праздники (старый обработчик — оставляем для совместимости)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "events:holidays")
async def events_holidays(callback: types.CallbackQuery):
    now = datetime.utcnow()
    month = now.month
    year = now.year

    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
    }

    lines = [f"🎉 <b>Праздники — {month_names[month]} {year}</b>\n"]

    month_holidays = [(m, d, name) for m, d, name in _RU_HOLIDAYS if m == month]
    if month_holidays:
        for m, d, name in sorted(month_holidays, key=lambda x: x[1]):
            lines.append(f"📅 <b>{d:02d}.{m:02d}</b> — {name}")
    else:
        lines.append("<i>В этом месяце государственных праздников нет.</i>")

    lines.append("\n<i>Следующие праздники:</i>")
    # Показать ближайшие 2 праздника из других месяцев
    future = []
    for m, d, name in _RU_HOLIDAYS:
        try:
            hdate = datetime(year, m, d)
        except ValueError:
            continue
        if hdate < now:
            hdate = datetime(year + 1, m, d)
        if hdate.month != month:
            future.append((hdate, name))
    future.sort()
    for hdate, name in future[:3]:
        lines.append(f"  {hdate.strftime('%d.%m')} — {name}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_btn("menu:events", "← К событиям"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Дни рождения
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "events:birthdays")
async def events_birthdays(callback: types.CallbackQuery):
    events = await get_upcoming_events(event_type="birthday", days=365)
    now = datetime.utcnow()

    if not events:
        text = (
            "🎂 <b>Дни рождения сотрудников</b>\n\n"
            "<i>Список пуст. Добавить дни рождения может администратор.</i>"
        )
    else:
        lines = ["🎂 <b>Дни рождения сотрудников</b>\n"]
        upcoming = []
        for e in events:
            # Подбираем ближайшую дату (в этом или следующем году)
            try:
                bday = e.event_date.replace(year=now.year)
            except ValueError:
                bday = e.event_date.replace(year=now.year, day=28)
            if bday < now.replace(hour=0, minute=0, second=0):
                try:
                    bday = bday.replace(year=now.year + 1)
                except ValueError:
                    bday = bday.replace(year=now.year + 1, day=28)
            days_left = (bday.date() - now.date()).days
            upcoming.append((days_left, bday, e.title))

        upcoming.sort()
        for days_left, bday, name in upcoming:
            date_str = bday.strftime("%d.%m")
            if days_left == 0:
                marker = "🎉 СЕГОДНЯ!"
            elif days_left == 1:
                marker = "🔔 Завтра"
            elif days_left <= 7:
                marker = f"🟡 Через {days_left} дн."
            else:
                marker = f"📅 {date_str}"
            lines.append(f"{marker} — {name}")

        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=_back_btn("menu:events", "← К событиям"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Добавить бронь (FSM, только manager/admin)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "events:add_booking")
async def add_booking_start(callback: types.CallbackQuery, state: FSMContext):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.role not in _MANAGER_ROLES:
        await callback.answer("⛔ Только для менеджеров и администраторов", show_alert=True)
        return

    await state.set_state(EventAddBookingState.waiting_name)
    await callback.message.edit_text(
        "📋 <b>Добавление брони</b>\n\n"
        "Введите имя гостя или название брони:\n\n"
        "<i>Например: Иванов Иван, 4 персоны</i>",
        reply_markup=_back_btn("menu:events", "✖ Отмена"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EventAddBookingState.waiting_name)
async def booking_got_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(EventAddBookingState.waiting_date)
    await message.answer(
        "📅 Введите дату брони в формате <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>:\n"
        "<i>Например: 25.07 или 25.07.2026</i>",
        parse_mode="HTML",
    )


@router.message(EventAddBookingState.waiting_date)
async def booking_got_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        if len(text) <= 5:
            dt = datetime.strptime(f"{text}.{datetime.utcnow().year}", "%d.%m.%Y")
        else:
            dt = datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Введите дату как <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>:", parse_mode="HTML")
        return
    await state.update_data(date=dt)
    await state.set_state(EventAddBookingState.waiting_time)
    await message.answer(
        "⏰ Введите время брони в формате <b>ЧЧ:ММ</b>:\n<i>Например: 19:00</i>",
        parse_mode="HTML",
    )


@router.message(EventAddBookingState.waiting_time)
async def booking_got_time(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        t = datetime.strptime(text, "%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Введите время как <b>ЧЧ:ММ</b>:", parse_mode="HTML")
        return
    data = await state.get_data()
    dt: datetime = data["date"]
    dt = dt.replace(hour=t.hour, minute=t.minute)
    await state.update_data(datetime=dt)
    await state.set_state(EventAddBookingState.waiting_guests)
    await message.answer("👥 Введите количество гостей:")


@router.message(EventAddBookingState.waiting_guests)
async def booking_got_guests(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введите число:")
        return
    await state.update_data(guests=int(text))
    await state.set_state(EventAddBookingState.waiting_phone)
    await message.answer(
        "📞 Введите телефон гостя (или <b>-</b> если нет):",
        parse_mode="HTML",
    )


@router.message(EventAddBookingState.waiting_phone)
async def booking_got_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if phone == "-":
        phone = ""
    await state.update_data(phone=phone)
    await state.set_state(EventAddBookingState.waiting_comment)
    await message.answer(
        "💬 Пожелания/комментарий (или <b>-</b> если нет):",
        parse_mode="HTML",
    )


@router.message(EventAddBookingState.waiting_comment)
async def booking_got_comment(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    data = await state.get_data()

    event_id = await create_event(
        event_type="booking",
        title=data["name"],
        event_date=data["datetime"],
        meta={
            "guest_count": data["guests"],
            "phone": data["phone"],
            "comment": comment,
        },
        created_by=message.from_user.id,
    )

    dt: datetime = data["datetime"]
    await state.clear()
    await message.answer(
        f"✅ <b>Бронь добавлена!</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📅 Дата: {dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"👥 Гостей: {data['guests']}\n"
        f"📞 Телефон: {data['phone'] or '—'}\n"
        f"💬 Комментарий: {comment or '—'}",
        parse_mode="HTML",
        reply_markup=_back_btn("menu:events", "← К событиям"),
    )


# ────────────────────────────────────────────────────────────────────────────
#  Добавить анонс (FSM, только manager/admin)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "events:add_announcement")
async def add_announcement_start(callback: types.CallbackQuery, state: FSMContext):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.role not in _MANAGER_ROLES:
        await callback.answer("⛔ Только для менеджеров и администраторов", show_alert=True)
        return

    await state.set_state(EventAddAnnouncementState.waiting_title)
    await callback.message.edit_text(
        "📣 <b>Добавление анонса мероприятия</b>\n\n"
        "Введите название мероприятия:\n"
        "<i>Например: Винное казино — дегустация итальянских вин</i>",
        reply_markup=_back_btn("menu:events", "✖ Отмена"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EventAddAnnouncementState.waiting_title)
async def announcement_got_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(EventAddAnnouncementState.waiting_date)
    await message.answer(
        "📅 Введите дату и время мероприятия в формате <b>ДД.ММ ЧЧ:ММ</b>:\n"
        "<i>Например: 28.07 20:00</i>",
        parse_mode="HTML",
    )


@router.message(EventAddAnnouncementState.waiting_date)
async def announcement_got_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        year = datetime.utcnow().year
        dt = datetime.strptime(f"{text}.{year}", "%d.%m %H:%M.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Введите как <b>ДД.ММ ЧЧ:ММ</b>:", parse_mode="HTML")
        return
    await state.update_data(event_date=dt)
    await state.set_state(EventAddAnnouncementState.waiting_description)
    await message.answer(
        "📝 Введите описание (или <b>-</b> если не нужно):",
        parse_mode="HTML",
    )


@router.message(EventAddAnnouncementState.waiting_description)
async def announcement_got_description(message: types.Message, state: FSMContext):
    desc = message.text.strip()
    if desc == "-":
        desc = None
    data = await state.get_data()

    await create_event(
        event_type="announcement",
        title=data["title"],
        event_date=data["event_date"],
        description=desc,
        created_by=message.from_user.id,
    )

    dt: datetime = data["event_date"]
    await state.clear()
    await message.answer(
        f"✅ <b>Анонс добавлен!</b>\n\n"
        f"📣 {data['title']}\n"
        f"📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"📝 {desc or '—'}",
        parse_mode="HTML",
        reply_markup=_back_btn("menu:events", "← К событиям"),
    )
