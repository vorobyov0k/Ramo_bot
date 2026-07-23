"""Главное меню (home screen) бота RAMO."""
from datetime import datetime, timezone, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot import config
from bot.utils.db_connector import (
    get_user_by_telegram_id,
    get_active_shift,
    open_shift,
    close_shift,
    get_today_events_count,
    get_today_open_tasks_count,
)
from bot.utils.positions import (
    get_position_display, get_user_checklists, get_role_display_ui, MODERATOR_ROLES,
)
from bot.utils.tg_helpers import safe_edit

router = Router()

_PANEL_ROLES = MODERATOR_ROLES  # admin, pm, owner — доступ в режим модерации (менеджер — нет)
# Должности у которых есть смена (не менеджерские)
_SHIFT_POSITIONS = {"barman", "waiter", "cleaning", "cook", "chef", "owner"}
_SHIFT_ROLES = {"barman", "waiter", "security", "cook", "chef", "cleaning", "user"}
_ROLE_DEPT = {
    "barman": "bar",
    "waiter": "restaurant",
    "cook": "kitchen",
    "chef": "kitchen",
    "cleaning": "cleaning",
}
_WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _today_str() -> str:
    msk = timezone(timedelta(hours=3))
    now = datetime.now(msk)
    day = _WEEKDAYS[now.weekday()]
    return f"{day}, {now.day} {_MONTHS[now.month - 1]}"


def _build_home_keyboard(position: str, has_active_shift: bool) -> InlineKeyboardMarkup:
    buttons = []

    if position in _SHIFT_POSITIONS or position in _SHIFT_ROLES:
        if has_active_shift:
            buttons.append([InlineKeyboardButton(text="🔴 Закрыть смену", callback_data="home:end_shift")])
        else:
            buttons.append([InlineKeyboardButton(text="🟢 Начать смену", callback_data="home:start_shift")])

    buttons += [
        [
            InlineKeyboardButton(text="📚 Библиотека", callback_data="menu:library"),
            InlineKeyboardButton(text="🎁 Акции",      callback_data="menu:promos"),
        ],
        [
            InlineKeyboardButton(text="📋 Мои задачи", callback_data="menu:tasks"),
            InlineKeyboardButton(text="📅 События",    callback_data="menu:events"),
        ],
        [
            InlineKeyboardButton(text="🔄 Передача смены", callback_data="menu:handover"),
            InlineKeyboardButton(text="🆘 Инцидент",        callback_data="menu:incident"),
        ],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_home_screen(user) -> tuple[str, InlineKeyboardMarkup]:
    """Собирает текст и клавиатуру home screen для пользователя."""
    position_display = get_position_display(user)
    department = _ROLE_DEPT.get(user.position or user.role or "")

    events_count = await get_today_events_count()
    tasks_count = await get_today_open_tasks_count(user.telegram_id, department)
    active_shift = await get_active_shift(user.telegram_id)

    today = _today_str()

    lines = [
        f"👋 <b>Привет, {user.full_name}!</b>",
        f"👔 {position_display}  |  📅 {today}",
        "",
    ]

    # Блок "сегодня"
    if events_count or tasks_count:
        lines.append("📌 <b>Сегодня:</b>")
        if events_count:
            lines.append(f"  • 🗓 Событий: <b>{events_count}</b>")
        if tasks_count:
            lines.append(f"  • 📋 Открытых задач: <b>{tasks_count}</b>")
        lines.append("")

    if active_shift:
        msk = timezone(timedelta(hours=3))
        started = active_shift.started_at.replace(tzinfo=timezone.utc).astimezone(msk)
        lines.append(f"🟢 <b>Смена открыта</b> с {started.strftime('%H:%M')}")
        lines.append("")

    lines.append("Выбери раздел:")

    text = "\n".join(lines)
    position = user.position or user.role or ""
    keyboard = _build_home_keyboard(position, bool(active_shift))
    return text, keyboard


async def show_home_screen(trigger, user=None):
    """Показать home screen. trigger — Message или CallbackQuery."""
    if user is None:
        user_id = trigger.from_user.id
        user = await get_user_by_telegram_id(user_id)

    text, keyboard = await build_home_screen(user)

    if isinstance(trigger, types.CallbackQuery):
        # safe_edit: home screen часто открывают из фото-сообщения (карточка блюда
        # с фото), где edit_text падает — раньше это давало «зависание».
        await safe_edit(trigger, text, keyboard)
        await trigger.answer()
    else:
        await trigger.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ─── Callbacks ───

@router.callback_query(F.data == "menu:main")
async def callback_main_menu(callback: types.CallbackQuery):
    await show_home_screen(callback)


@router.callback_query(F.data == "home:start_shift")
async def start_shift(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    existing = await get_active_shift(user.telegram_id)
    if existing:
        await callback.answer("⚠️ Смена уже открыта", show_alert=True)
        return

    await open_shift(user.telegram_id, user.full_name)
    await callback.answer("✅ Смена начата!")
    await show_home_screen(callback, user)


@router.callback_query(F.data == "home:end_shift")
async def end_shift(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return

    shift = await get_active_shift(user.telegram_id)
    if not shift:
        await callback.answer("⚠️ Нет открытой смены", show_alert=True)
        return

    await close_shift(shift.shift_id)
    await callback.answer("✅ Смена закрыта!")
    await show_home_screen(callback, user)


@router.callback_query(F.data == "menu:settings")
async def settings_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    db_user = await get_user_by_telegram_id(user_id)
    role = db_user.role if db_user else None
    is_admin = (
        user_id == config.ADMIN_TELEGRAM_ID
        or (config.ADMIN_IDS and user_id in config.ADMIN_IDS)
        or role == "admin"
    )

    position_display = get_position_display(db_user) if db_user else "—"
    role_display = get_role_display_ui(role or "")
    info = (
        f"👤 Должность: <b>{position_display}</b>\n"
        f"🎭 Роль: <b>{role_display}</b>\n\n"
    )

    buttons = []
    if is_admin or role in _PANEL_ROLES:
        buttons.append([
            InlineKeyboardButton(text="🔧 Режим модерации", callback_data="admin:panel"),
        ])
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            + info
            + "📱 <b>Главное меню</b> — режим сотрудника:\n"
            "библиотека, задачи, события, передача смены, инциденты.\n\n"
            "🔧 <b>Режим модерации</b> — управление:\n"
            "пользователями, задачами, акциями, чек-листами, событиями, рассылками.\n\n"
            "<i>Профиль: обратитесь к Константину для изменения данных.</i>"
        )
    else:
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            + info
            + "<i>Для изменения данных обратитесь к менеджеру.</i>"
        )

    buttons.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_edit(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu:progress")
async def progress_menu(callback: types.CallbackQuery):
    text = (
        "📊 <b>Мой прогресс</b>\n\n"
        "Здесь будет отображаться твой прогресс онбординга.\n\n"
        "<i>Раздел в разработке.</i>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.message(Command("sync"))
async def cmd_sync(message: types.Message):
    if message.from_user.id != config.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    from bot.utils.cache_manager import get_cache_manager
    cache = get_cache_manager()
    result = await cache.sync_all()
    if result:
        await message.answer("✅ Кэш синхронизирован.")
    else:
        await message.answer("⚠️ Синхронизация завершена (данные из _SEED).")
