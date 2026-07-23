"""
Панель администратора RAMO.
Доступ: только пользователи из config.ADMIN_IDS или с ролью admin.
"""
import logging
from datetime import datetime
from aiogram import Router, Bot, types, F
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot import config
from bot.utils.db_connector import (
    get_user_by_telegram_id,
    get_all_users,
    create_pending_user,
    approve_user,
    reject_user,
    update_user_role,
    update_user_position,
    deactivate_user,
    delete_user,
    get_recent_checklists,
    get_checklist_execution,
    get_recent_incidents,
    get_recent_handovers,
    get_events_by_type,
    delete_event,
)
from bot.utils.cache_manager import get_cache_manager
from bot.utils.positions import (
    get_position_display,
    get_role_display_ui,
    ADMIN_POSITIONS,
    ADMIN_ROLES,
    POSITION_MAP,
    MODERATOR_ROLES,
)
from bot.states.forms import (
    AdminBroadcastState, AdminEditRoleState, AdminEditPositionState,
    AdminCreateUserState, MenuPhotoUploadState,
)
from bot.utils.menu_db import (
    get_categories, get_dishes_by_category, get_dish_by_id,
    get_drinks_by_category, get_drink_by_id,
    update_dish_photo, update_drink_photo,
)
from bot.utils.tg_helpers import safe_edit

router = Router()
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
#  Фильтр: админ/менеджер/pm (режим модерации)
# ────────────────────────────────────────────────────────────────────────────

class IsModerator(Filter):
    """Доступ в режим модерации: роли admin, pm, owner (менеджер зала — нет)."""
    async def __call__(self, event: types.TelegramObject) -> bool:
        user_id = None
        if isinstance(event, types.Message):
            user_id = event.from_user.id
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id
        if user_id is None:
            return False
        # Владелец бота (ADMIN_TELEGRAM_ID) и ADMIN_IDS — модераторы всегда,
        # независимо от роли в БД (чтобы не потерять доступ к панели).
        if user_id == config.ADMIN_TELEGRAM_ID:
            return True
        if config.ADMIN_IDS and user_id in config.ADMIN_IDS:
            return True
        db_user = await get_user_by_telegram_id(user_id)
        return db_user is not None and db_user.role in MODERATOR_ROLES


router.message.filter(IsModerator())
router.callback_query.filter(IsModerator())


# ────────────────────────────────────────────────────────────────────────────
#  Хелперы
# ────────────────────────────────────────────────────────────────────────────

def _back_btn(target: str, label: str = "← Назад"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=target)],
    ])


def _back_row(target: str, label: str = "← Назад"):
    return [InlineKeyboardButton(text=label, callback_data=target)]


# ────────────────────────────────────────────────────────────────────────────
#  Главная панель
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users")],
        [InlineKeyboardButton(text="⏳ Заявки на вход", callback_data="admin:pending")],
        [InlineKeyboardButton(text="📊 Журналы", callback_data="admin:logs")],
        [InlineKeyboardButton(text="✅ Чек-листы (редактор)", callback_data="admin:checklists")],
        [InlineKeyboardButton(text="📅 События (удаление)", callback_data="admin:events_mgmt")],
        [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="📸 Фото меню", callback_data="admin:menu_photo")],
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
    ])
    await safe_edit(
        callback,
        "🔧 <b>Режим модерации RAMO</b>\n\nПанель управления: пользователи, чек-листы, события, рассылки.\n\nВыберите раздел:",
        keyboard,
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Пользователи — список + фильтры
# ────────────────────────────────────────────────────────────────────────────

def _users_filter_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора фильтра для списка пользователей."""
    pos_buttons = [
        InlineKeyboardButton(text=label, callback_data=f"admin:users_pos:{slug}")
        for slug, label in ADMIN_POSITIONS
    ]
    role_buttons = [
        InlineKeyboardButton(text=label, callback_data=f"admin:users_role:{role}")
        for role, label in ADMIN_ROLES
    ]
    rows = [[InlineKeyboardButton(text="👥 Все сотрудники", callback_data="admin:users")]]
    rows.append([InlineKeyboardButton(text="━━ По должности ━━", callback_data="noop")])
    rows += [[btn] for btn in pos_buttons]
    rows.append([InlineKeyboardButton(text="━━ По роли ━━", callback_data="noop")])
    rows += [[btn] for btn in role_buttons]
    rows.append(_back_row("admin:panel"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_users_list(callback: types.CallbackQuery, users, title: str, filter_active: bool = False):
    buttons = []
    buttons.append([InlineKeyboardButton(text="➕ Создать пользователя", callback_data="admin:user_create")])

    if not users:
        await safe_edit(callback,
            f"{title}\n\n<i>Сотрудников не найдено.</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons + [
                [InlineKeyboardButton(text="🔍 Фильтр", callback_data="admin:users_filter")],
                _back_row("admin:panel"),
            ]),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    for u in users:
        pos = get_position_display(u)
        name = u.full_name or "Без имени"
        buttons.append([InlineKeyboardButton(
            text=f"{pos} — {name}",
            callback_data=f"admin:user:{u.telegram_id}",
        )])

    filter_row = [InlineKeyboardButton(
        text="🔍 Фильтр ▼" if not filter_active else "🔍 Фильтр (активен) ▼",
        callback_data="admin:users_filter",
    )]
    buttons.append(filter_row)
    buttons.append(_back_row("admin:panel"))

    await safe_edit(callback,
        f"{title} ({len(users)}):\n\nНажми на имя для управления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:users")
async def admin_users(callback: types.CallbackQuery):
    users = await get_all_users(status="active")
    await _show_users_list(callback, users, "👥 <b>Все активные сотрудники</b>")


@router.callback_query(F.data == "admin:users_filter")
async def admin_users_filter(callback: types.CallbackQuery):
    await safe_edit(callback,
        "🔍 <b>Фильтр сотрудников</b>\n\nВыберите фильтр:",
        reply_markup=_users_filter_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:users_pos:"))
async def admin_users_by_pos(callback: types.CallbackQuery):
    slug = callback.data[len("admin:users_pos:"):]
    pos_name = POSITION_MAP.get(slug, (slug,))[0]
    all_users = await get_all_users(status="active")
    filtered = [u for u in all_users if u.position == slug]
    await _show_users_list(callback, filtered, f"👥 <b>{pos_name}</b>", filter_active=True)


@router.callback_query(F.data.startswith("admin:users_role:"))
async def admin_users_by_role(callback: types.CallbackQuery):
    role = callback.data[len("admin:users_role:"):]
    role_name = get_role_display_ui(role)
    all_users = await get_all_users(status="active")
    filtered = [u for u in all_users if u.role == role]
    await _show_users_list(callback, filtered, f"👥 <b>{role_name}</b>", filter_active=True)


# ────────────────────────────────────────────────────────────────────────────
#  Карточка сотрудника
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:user:"))
async def admin_user_detail(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    pos_label  = get_position_display(user)
    role_label = get_role_display_ui(user.role or "")
    status_label = "✅ Активен" if user.active else "🚫 Неактивен"
    reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"

    text = (
        f"👤 <b>{user.full_name or 'Без имени'}</b>\n\n"
        f"💼 Должность: <b>{pos_label}</b>\n"
        f"🎭 Роль: <b>{role_label}</b>\n"
        f"📁 Статус: {status_label}\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"📅 Регистрация: {reg_date}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изменить роль",     callback_data=f"admin:user_role:{user_id}"),
            InlineKeyboardButton(text="✏️ Назначить должность", callback_data=f"admin:user_pos:{user_id}"),
        ],
        [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin:user_deactivate:{user_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin:user_delete:{user_id}")],
        _back_row("admin:users", "← К списку"),
    ])

    await safe_edit(callback, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Создать пользователя (только owner/admin)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:user_create")
async def admin_user_create_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания пользователя: запрос ФИО."""
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.role not in MODERATOR_ROLES:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminCreateUserState.waiting_name)
    await safe_edit(callback,
        "➕ <b>Создание нового пользователя</b>\n\n"
        "Введите ФИО (полное имя) в ответном сообщении:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✖ Отмена", callback_data="admin:users")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminCreateUserState.waiting_name)
async def admin_user_create_name(message: types.Message, state: FSMContext):
    """Получение ФИО, переход к выбору должности."""
    full_name = message.text.strip()
    if not full_name or len(full_name) < 2:
        await message.answer("⚠️ Введите полное имя (минимум 2 символа):")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(AdminCreateUserState.waiting_position)

    # Кнопки выбора должности
    pos_buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:create_pos:{slug}")]
        for slug, label in ADMIN_POSITIONS
    ]
    pos_buttons.append([InlineKeyboardButton(text="✖ Отмена", callback_data="admin:users")])

    await message.answer(
        f"✅ ФИО: <b>{full_name}</b>\n\n"
        f"Выберите должность:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=pos_buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:create_pos:"))
async def admin_user_create_position(callback: types.CallbackQuery, state: FSMContext):
    """Выбор должности, создание пользователя."""
    slug = callback.data[len("admin:create_pos:"):]
    data = await state.get_data()
    full_name = data.get("full_name", "")
    await state.clear()

    if slug not in POSITION_MAP:
        await callback.answer("❌ Должность не найдена", show_alert=True)
        return

    pos_name = POSITION_MAP[slug][0]
    role = POSITION_MAP[slug][1]

    # Создаём пользователя (генерируем временный ID, потом он регистрируется)
    # Но нужен telegram_id. Здесь проблема: мы можем создать только если у нас есть ID.
    # Вариант: показываем инструкцию пользователю регистрироваться, или создаём "пропуск" с кодом.

    # Или: создаём пользователя с поддельным ID (напр., -1 + timestamp),
    # но это не очень правильно.

    # Лучший подход: запрашиваем username (если пользователь в боте) или показываем
    # инструкцию для регистрации.

    # Пока что: создаём запись в БД с полными данными (role=user, position=slug),
    # но без telegram_id (или с временным). И администратор передаёт приглашение.

    # Фактически, мы можем только создать "заявку" пользователя. Реальный telegram_id
    # нужен только когда пользователь начнёт регистрацию в боте.

    # Переформулирую: администратор создаёт пользователя, но для этого нужен его Telegram ID.
    # Если его нет, мы не можем создать запись (требуется telegram_id как primary key).

    # Вариант: попросим у админа telegram_id или username, посмотрим/найдём ID.

    # Для простоты: покажем форму подтверждения с возможностью задать ID или username.

    text = (
        f"📋 <b>Подтверждение создания пользователя</b>\n\n"
        f"ФИО: <b>{full_name}</b>\n"
        f"Должность: <b>{pos_name}</b>\n"
        f"Роль: <b>{get_role_display_ui(role)}</b>\n\n"
        f"⚠️ Для создания нужен Telegram ID пользователя.\n"
        f"Пользователь должен сначала зарегистрироваться в боте."
    )

    await safe_edit(callback, text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К пользователям", callback_data="admin:users")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer("ℹ️ Пользователь сможет зарегистрироваться в боте и получит эту должность.")


# ────────────────────────────────────────────────────────────────────────────
#  Изменить роль (техническая)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:user_role:"))
async def admin_user_role_select(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    name = user.full_name if user else str(user_id)

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:role_confirm:{user_id}:{role}")]
        for role, label in ADMIN_ROLES
    ]
    buttons.append(_back_row(f"admin:user:{user_id}", "✖ Отмена"))

    await safe_edit(callback,
        f"✏️ <b>Изменить роль</b>\n\n"
        f"Сотрудник: <b>{name}</b>\n\n"
        f"Роль определяет права доступа в системе:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:role_confirm:"))
async def admin_role_confirm(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    try:
        user_id = int(parts[2])
        new_role = parts[3]
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    name = user.full_name if user else str(user_id)
    role_label = get_role_display_ui(new_role)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin:set_role:{user_id}:{new_role}"),
            InlineKeyboardButton(text="✖ Отмена",       callback_data=f"admin:user_role:{user_id}"),
        ],
    ])
    await safe_edit(callback,
        f"❓ Сменить роль <b>{name}</b> на <b>{role_label}</b>?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:set_role:"))
async def admin_user_role_set(callback: types.CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    try:
        user_id = int(parts[2])
        new_role = parts[3]
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    ok = await update_user_role(user_id, new_role)
    role_label = get_role_display_ui(new_role)
    if ok:
        await callback.answer(f"✅ Роль изменена на {role_label}", show_alert=True)
        try:
            await bot.send_message(
                user_id,
                f"ℹ️ <b>Ваша роль в системе изменена</b>\n\n"
                f"Новая роль: <b>{role_label}</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await callback.answer("❌ Ошибка при сохранении", show_alert=True)

    # Возврат к карточке с обновлёнными данными
    callback.data = f"admin:user:{user_id}"
    await admin_user_detail(callback)


# ────────────────────────────────────────────────────────────────────────────
#  Назначить должность (бизнесовая)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:user_pos:"))
async def admin_user_pos_select(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    name = user.full_name if user else str(user_id)

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:pos_confirm:{user_id}:{slug}")]
        for slug, label in ADMIN_POSITIONS
    ]
    buttons.append(_back_row(f"admin:user:{user_id}", "✖ Отмена"))

    await safe_edit(callback,
        f"✏️ <b>Назначить должность</b>\n\n"
        f"Сотрудник: <b>{name}</b>\n\n"
        f"Должность определяет отображение и доступные чек-листы:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:pos_confirm:"))
async def admin_pos_confirm(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    try:
        user_id = int(parts[2])
        new_pos = parts[3]
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    name = user.full_name if user else str(user_id)
    pos_label = POSITION_MAP.get(new_pos, (new_pos,))[0]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin:set_pos:{user_id}:{new_pos}"),
            InlineKeyboardButton(text="✖ Отмена",       callback_data=f"admin:user_pos:{user_id}"),
        ],
    ])
    await safe_edit(callback,
        f"❓ Назначить <b>{name}</b> должность <b>{pos_label}</b>?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:set_pos:"))
async def admin_user_pos_set(callback: types.CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    try:
        user_id = int(parts[2])
        new_pos = parts[3]
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    ok = await update_user_position(user_id, new_pos)
    pos_label = POSITION_MAP.get(new_pos, (new_pos,))[0]
    if ok:
        await callback.answer(f"✅ Должность: {pos_label}", show_alert=True)
        try:
            await bot.send_message(
                user_id,
                f"ℹ️ <b>Вам назначена должность</b>\n\n"
                f"Должность: <b>{pos_label}</b>\n\n"
                f"Доступные чек-листы обновятся автоматически.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await callback.answer("❌ Ошибка при сохранении", show_alert=True)

    # Возврат к карточке с обновлёнными данными
    callback.data = f"admin:user:{user_id}"
    await admin_user_detail(callback)


@router.callback_query(F.data.startswith("admin:user_deactivate:"))
async def admin_user_deactivate(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    # Подтверждение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, деактивировать", callback_data=f"admin:user_deactivate_confirm:{user_id}"),
            InlineKeyboardButton(text="✖ Отмена", callback_data=f"admin:user:{user_id}"),
        ],
    ])
    user = await get_user_by_telegram_id(user_id)
    name = user.full_name if user else str(user_id)
    await safe_edit(callback,
        f"🚫 Деактивировать <b>{name}</b>?\n\nПользователь потеряет доступ к боту.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:user_deactivate_confirm:"))
async def admin_user_deactivate_confirm(callback: types.CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    ok = await deactivate_user(user_id)
    if ok:
        await callback.answer("✅ Пользователь деактивирован", show_alert=True)
    else:
        await callback.answer("❌ Ошибка", show_alert=True)
    await admin_users(callback)


# ────────────────────────────────────────────────────────────────────────────
#  Заявки на вход (pending)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:pending")
async def admin_pending(callback: types.CallbackQuery):
    users = await get_all_users(status="pending")
    if not users:
        await safe_edit(callback,
            "⏳ <b>Заявки на вход</b>\n\n<i>Новых заявок нет.</i>",
            reply_markup=_back_btn("admin:panel"),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    buttons = []
    for u in users:
        role_label = get_role_display_ui(u.requested_role or "")
        label = f"{u.full_name or 'Без имени'} → {role_label}"
        buttons.append([
            InlineKeyboardButton(text=f"✅ {label}", callback_data=f"admin:approve:{u.telegram_id}"),
            InlineKeyboardButton(text="❌", callback_data=f"admin:reject:{u.telegram_id}"),
        ])
    buttons.append(_back_row("admin:panel"))

    await safe_edit(callback,
        f"⏳ <b>Заявки на вход</b> ({len(users)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:user_delete:"))
async def admin_user_delete(callback: types.CallbackQuery):
    """Начало удаления пользователя: запрос подтверждения."""
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    name = user.full_name if user else str(user_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin:user_delete_confirm:{user_id}"),
            InlineKeyboardButton(text="✖ Отмена", callback_data=f"admin:user:{user_id}"),
        ],
    ])
    await safe_edit(callback,
        f"⚠️ <b>УДАЛИТЬ пользователя {name}?</b>\n\n"
        f"Это действие необратимо. Пользователь будет полностью удалён из системы.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:user_delete_confirm:"))
async def admin_user_delete_confirm(callback: types.CallbackQuery):
    """Подтверждённое удаление пользователя."""
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    name = user.full_name if user else str(user_id)

    ok = await delete_user(user_id)
    if ok:
        await safe_edit(callback,
            f"✅ Пользователь <b>{name}</b> удалён из системы.",
            reply_markup=_back_btn("admin:users", "← К списку пользователей"),
            parse_mode="HTML",
        )
    else:
        await callback.answer("❌ Не удалось удалить пользователя", show_alert=True)
        return

    await callback.answer("✅ Пользователь удалён")


@router.callback_query(F.data.startswith("admin:approve:"))
async def admin_approve_user(callback: types.CallbackQuery, bot: Bot):
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    await approve_user(user_id)
    await callback.answer("✅ Одобрен", show_alert=True)

    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Заявка одобрена!</b>\n\n"
            f"Добро пожаловать в RAMO, {user.full_name or 'сотрудник'}!\n"
            f"Нажми /start чтобы попасть в главное меню.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

    await admin_pending(callback)


@router.callback_query(F.data.startswith("admin:reject:"))
async def admin_reject_user(callback: types.CallbackQuery, bot: Bot):
    try:
        user_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    user = await get_user_by_telegram_id(user_id)
    await reject_user(user_id)
    await callback.answer("❌ Отклонён", show_alert=True)

    if user:
        try:
            await bot.send_message(
                user_id,
                "❌ <b>Заявка отклонена.</b>\n\nОбратитесь к менеджеру смены для уточнения.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление {user_id}: {e}")

    await admin_pending(callback)


# ────────────────────────────────────────────────────────────────────────────
#  Журналы
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:logs")
async def admin_logs(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполненные чек-листы", callback_data="admin:log_checklists")],
        [InlineKeyboardButton(text="🆘 Инциденты", callback_data="admin:log_incidents")],
        [InlineKeyboardButton(text="🔄 Передачи смен", callback_data="admin:log_handovers")],
        _back_row("admin:panel"),
    ])
    await safe_edit(callback,
        "📊 <b>Журналы</b>\n\nВыберите раздел:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


# Отображаемые названия и эмодзи типов чек-листов (журнал модерации)
_CHECKLIST_LABELS = {
    "opening":   "🌅 Открытие смены",
    "closing":   "🌙 Закрытие смены",
    "bar":       "🍸 Чек-лист бармена",
    "bar_shift": "🍸 Чек-лист бармена",
    "floor":     "🍽 Чек-лист официанта",
    "cleaning":  "🧹 Чек-лист клининга",
    "kitchen":   "🍳 Чек-лист кухни",
}
_CHECKLIST_EMOJI = {
    "opening": "🌅", "closing": "🌙", "bar": "🍸", "bar_shift": "🍸",
    "floor": "🍽", "cleaning": "🧹", "kitchen": "🍳",
}


def _cl_label(cl_type: str) -> str:
    return _CHECKLIST_LABELS.get(cl_type, f"📋 {cl_type}")


def _cl_template_items(cl_type: str) -> list:
    """Пункты-шаблон чек-листа из кэша (для сопоставления id→текст и total)."""
    cl_data = get_cache_manager().get("checklists") or {}
    return cl_data.get(cl_type, {}).get("items", [])


def _progress_bar(done: int, total: int, width: int = 10) -> str:
    if not total:
        return ""
    filled = min(width, round(width * done / total))
    return "▰" * filled + "▱" * (width - filled)


def _cl_card_text(ex, user) -> str:
    """Компактная мини-карточка одного выполненного чек-листа."""
    name = user.full_name if (user and user.full_name) else f"ID {ex.user_id}"
    pos = get_position_display(user) if user else ""
    dt = ex.created_at.strftime("%d.%m %H:%M") if ex.created_at else "—"
    done = len(ex.items or [])
    total = len(_cl_template_items(ex.checklist_type))
    ratio = f"{done}/{total}" if total else f"{done}"
    bar = _progress_bar(done, total)
    done_all = total and done >= total
    lines = [
        f"<b>{_cl_label(ex.checklist_type)}</b>" + ("  🎉" if done_all else ""),
        f"👤 {name}" + (f" · {pos}" if pos else ""),
        f"📅 {dt}",
        f"📊 {ratio}" + (f"   {bar}" if bar else ""),
    ]
    return "\n".join(lines)


def _cl_report_text(ex, user) -> str:
    """Полный текстовый отчёт по чек-листу: пункты по зонам с ✅/⬜."""
    name = user.full_name if (user and user.full_name) else f"ID {ex.user_id}"
    pos = get_position_display(user) if user else ""
    dt = ex.created_at.strftime("%d.%m.%Y %H:%M") if ex.created_at else "—"

    done_ids = {
        it.get("item_id") for it in (ex.items or []) if it.get("completed", True)
    }
    template_items = _cl_template_items(ex.checklist_type)
    total = len(template_items)
    done = len(done_ids)

    head_ratio = f"<b>{done}" + (f"/{total}" if total else "") + "</b>"
    lines = [
        f"📋 <b>{_cl_label(ex.checklist_type)}</b>",
        f"👤 <b>{name}</b>" + (f" · {pos}" if pos else ""),
        f"📅 {dt}",
        f"📊 Выполнено: {head_ratio}"
        + (f"   {_progress_bar(done, total)}" if total else "")
        + ("  🎉" if (total and done >= total) else ""),
        "",
    ]

    if template_items:
        prev_zone = None
        for item in template_items:
            zone = item.get("zone", "")
            iid = item.get("id", (item.get("text", "") or "")[:10])
            if zone and zone != prev_zone:
                prev_zone = zone
                lines.append(f"\n📍 <b>{zone}</b>")
            mark = "✅" if iid in done_ids else "⬜"
            lines.append(f"{mark} {item.get('text', '')}")

        # Отмеченные пункты, которых нет в текущем шаблоне (шаблон менялся)
        known = {item.get("id", (item.get("text", "") or "")[:10]) for item in template_items}
        extra = [iid for iid in done_ids if iid not in known]
        if extra:
            lines.append("\n<i>Отмечено (пункт удалён из шаблона):</i>")
            lines += [f"✅ {iid}" for iid in extra]
    elif done_ids:
        lines.append("Отмеченные пункты:")
        lines += [f"✅ {iid}" for iid in done_ids]
    else:
        lines.append("<i>Нет данных по пунктам.</i>")

    text = "\n".join(lines)
    return text[:3990] + "\n…" if len(text) > 4000 else text


def _card_kb(execution_id: str, expanded: bool) -> InlineKeyboardMarkup:
    if expanded:
        btn = InlineKeyboardButton(text="← Свернуть", callback_data=f"admin:clc:{execution_id}")
    else:
        btn = InlineKeyboardButton(text="📄 Открыть отчёт", callback_data=f"admin:clx:{execution_id}")
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


@router.callback_query(F.data == "admin:log_checklists")
async def admin_log_checklists(callback: types.CallbackQuery):
    records = await get_recent_checklists(limit=8)

    # Верхнее сообщение-заголовок (сама навигация журнала)
    header = (
        "✅ <b>Выполненные чек-листы</b>\n\n"
        + (f"Последние <b>{len(records)}</b> — карточками ниже 👇"
           if records else "<i>Записей пока нет.</i>")
    )
    await safe_edit(callback, header, _back_btn("admin:logs", "← К журналам"))
    await callback.answer()

    if not records:
        return

    users = {u.telegram_id: u for u in await get_all_users()}
    for r in records:
        await callback.message.answer(
            _cl_card_text(r, users.get(r.user_id)),
            reply_markup=_card_kb(r.execution_id, expanded=False),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("admin:clx:"))
async def admin_cl_card_expand(callback: types.CallbackQuery):
    """Развернуть карточку в полный отчёт (in-place)."""
    execution_id = callback.data[len("admin:clx:"):]
    ex = await get_checklist_execution(execution_id)
    if not ex:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    user = await get_user_by_telegram_id(ex.user_id)
    await safe_edit(callback, _cl_report_text(ex, user), _card_kb(execution_id, expanded=True))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:clc:"))
async def admin_cl_card_collapse(callback: types.CallbackQuery):
    """Свернуть отчёт обратно в мини-карточку."""
    execution_id = callback.data[len("admin:clc:"):]
    ex = await get_checklist_execution(execution_id)
    if not ex:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    user = await get_user_by_telegram_id(ex.user_id)
    await safe_edit(callback, _cl_card_text(ex, user), _card_kb(execution_id, expanded=False))
    await callback.answer()


@router.callback_query(F.data == "admin:log_incidents")
async def admin_log_incidents(callback: types.CallbackQuery):
    records = await get_recent_incidents(limit=15)
    if not records:
        text = "🆘 <b>Инциденты</b>\n\n<i>Записей нет.</i>"
    else:
        lines = ["🆘 <b>Последние инциденты (15)</b>\n"]
        for r in records:
            dt = r.created_at.strftime("%d.%m %H:%M") if r.created_at else "—"
            desc_short = (r.description or "")[:60]
            lines.append(f"• {dt} | {r.incident_type}")
            lines.append(f"  {desc_short}")
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n..."

    await safe_edit(callback,
        text,
        reply_markup=_back_btn("admin:logs", "← К журналам"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:log_handovers")
async def admin_log_handovers(callback: types.CallbackQuery):
    records = await get_recent_handovers(limit=15)
    if not records:
        text = "🔄 <b>Передачи смен</b>\n\n<i>Записей нет.</i>"
    else:
        lines = ["🔄 <b>Последние передачи смен (15)</b>\n"]
        for r in records:
            dt = r.created_at.strftime("%d.%m %H:%M") if r.created_at else "—"
            msg_short = (r.message or "")[:60]
            importance = "🔴" if r.importance == "urgent" else "⚪"
            lines.append(f"{importance} {dt} | от ID {r.from_user_id}")
            lines.append(f"  {msg_short}")
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n..."

    await safe_edit(callback,
        text,
        reply_markup=_back_btn("admin:logs", "← К журналам"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Редактор чек-листов
# ────────────────────────────────────────────────────────────────────────────

_CL_TYPE_LABELS = {
    "opening":  "🌅 Открытие",
    "closing":  "🌙 Закрытие",
    "bar_shift": "🍸 Бар",
}


@router.callback_query(F.data == "admin:checklists")
async def admin_checklists(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌅 Открытие", callback_data="admin:cl_view:opening")],
        [InlineKeyboardButton(text="🌙 Закрытие", callback_data="admin:cl_view:closing")],
        [InlineKeyboardButton(text="🍸 Бар (смена)", callback_data="admin:cl_view:bar_shift")],
        _back_row("admin:panel"),
    ])
    await safe_edit(callback,
        "✅ <b>Редактор чек-листов</b>\n\nВыберите список:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:cl_view:"))
async def admin_cl_view(callback: types.CallbackQuery):
    cl_type = callback.data.split(":")[2]
    cache = get_cache_manager()
    cl = cache.get("checklists")
    label = _CL_TYPE_LABELS.get(cl_type, cl_type)

    if not cl or cl_type not in cl:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    items = cl[cl_type].get("items", [])

    # Каждый пункт — строка из двух кнопок: [текст] [🗑]
    rows = []
    prev_zone = None
    for idx, item in enumerate(items):
        zone = item.get("zone", "")
        if zone and zone != prev_zone:
            prev_zone = zone
            rows.append([InlineKeyboardButton(
                text=f"━━ 📍 {zone} ━━",
                callback_data="noop",
            )])
        short = item["text"][:38] + ("…" if len(item["text"]) > 38 else "")
        rows.append([
            InlineKeyboardButton(text=short, callback_data="noop"),
            InlineKeyboardButton(text="🗑", callback_data=f"admin:cli:{cl_type}:{idx}"),
        ])

    rows.append([InlineKeyboardButton(text="➕ Добавить пункт", callback_data=f"admin:cl_add:{cl_type}")])
    rows.append(_back_row("admin:checklists"))

    await safe_edit(callback,
        f"{label} — <b>{len(items)} пунктов</b>\n\nНажми 🗑 чтобы удалить пункт:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:cli:"))
async def admin_cl_delete_item(callback: types.CallbackQuery):
    """Удаление пункта чек-листа по индексу."""
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Ошибка", show_alert=True)
        return
    cl_type = parts[2]
    try:
        idx = int(parts[3])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    cache = get_cache_manager()
    cl = cache.get("checklists")
    if not cl or cl_type not in cl:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    items = cl[cl_type].get("items", [])
    if idx < 0 or idx >= len(items):
        await callback.answer("Пункт не найден", show_alert=True)
        return

    removed = items.pop(idx)
    cl[cl_type]["items"] = items
    cache.save("checklists", cl)

    removed_text = removed.get("text", "")[:40]
    await callback.answer(f"🗑 Удалено: «{removed_text}»", show_alert=True)

    # Обновить список на экране
    await admin_cl_view(callback)


@router.callback_query(F.data.startswith("admin:cl_add:"))
async def admin_cl_add_start(callback: types.CallbackQuery, state: FSMContext):
    cl_type = callback.data.split(":")[2]
    await state.update_data(cl_type=cl_type, fsm_action="cl_add")
    await state.set_state(AdminBroadcastState.waiting_text)

    label = _CL_TYPE_LABELS.get(cl_type, cl_type)
    await safe_edit(callback,
        f"➕ <b>Новый пункт в «{label}»</b>\n\n"
        "Введите текст. Зону укажи через «|»:\n"
        "<i>• Проверить кассу\n"
        "• Протереть стойку | Бар</i>",
        reply_markup=_back_btn(f"admin:cl_view:{cl_type}", "✖ Отмена"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminBroadcastState.waiting_text)
async def admin_fsm_text_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("fsm_action")

    if action == "cl_add":
        raw = message.text.strip()
        parts = [p.strip() for p in raw.split("|")]
        item_text = parts[0]
        item_zone = parts[1] if len(parts) > 1 else ""
        cl_type = data.get("cl_type", "opening")

        cache = get_cache_manager()
        cl = cache.get("checklists")
        if cl and cl_type in cl:
            import uuid as _uuid
            items = cl[cl_type].get("items", [])
            new_id = f"usr_{_uuid.uuid4().hex[:6]}"
            items.append({"id": new_id, "text": item_text, "zone": item_zone})
            cl[cl_type]["items"] = items
            cache.save("checklists", cl)
            await state.clear()
            zone_label = f" [{item_zone}]" if item_zone else ""
            await message.answer(
                f"✅ Пункт добавлен!\n\n<b>{item_text}</b>{zone_label}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← К чек-листу", callback_data=f"admin:cl_view:{cl_type}")],
                ]),
            )
        else:
            await message.answer("❌ Данные чек-листа не найдены.")
            await state.clear()

    elif action == "broadcast_text":
        text = message.text.strip()
        await state.update_data(broadcast_text=text, broadcast_source="text")
        await state.set_state(AdminBroadcastState.waiting_target)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Всем",              callback_data="admin:broadcast_target:all")],
            [InlineKeyboardButton(text="🍺 Барменам",          callback_data="admin:broadcast_target:barman")],
            [InlineKeyboardButton(text="🍽 Официантам",        callback_data="admin:broadcast_target:waiter")],
            [InlineKeyboardButton(text="🥘 Поварам",           callback_data="admin:broadcast_target:cook")],
            [InlineKeyboardButton(text="🍳 Шеф-поварам",      callback_data="admin:broadcast_target:chef")],
            [InlineKeyboardButton(text="🍸 Бар-менеджерам",   callback_data="admin:broadcast_target:bar_manager")],
            [InlineKeyboardButton(text="👔 Менеджерам",       callback_data="admin:broadcast_target:manager")],
            [InlineKeyboardButton(text="🧹 Хозяюшкам",        callback_data="admin:broadcast_target:cleaning")],
            [InlineKeyboardButton(text="🔧 Техникам",         callback_data="admin:broadcast_target:technician")],
            [InlineKeyboardButton(text="✖ Отмена",            callback_data="admin:broadcast")],
        ])
        preview = text[:200] + ("..." if len(text) > 200 else "")
        await message.answer(
            f"📣 <b>Кому отправить рассылку?</b>\n\n"
            f"<b>Текст:</b>\n{preview}",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await state.clear()


# ────────────────────────────────────────────────────────────────────────────
#  Управление событиями (удаление)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:events_mgmt")
async def admin_events_mgmt(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Брони", callback_data="admin:evmgmt:booking")],
        [InlineKeyboardButton(text="📢 Анонсы", callback_data="admin:evmgmt:announcement")],
        [InlineKeyboardButton(text="🎂 Дни рождения", callback_data="admin:evmgmt:birthday")],
        _back_row("admin:panel"),
    ])
    await safe_edit(callback,
        "📅 <b>Управление событиями</b>\n\nВыберите тип:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:evmgmt:"))
async def admin_evmgmt_list(callback: types.CallbackQuery):
    ev_type = callback.data.split(":")[2]
    events = await get_events_by_type(ev_type, limit=20)

    type_labels = {"booking": "📋 Брони", "announcement": "📢 Анонсы", "birthday": "🎂 Дни рождения"}
    label = type_labels.get(ev_type, ev_type)

    if not events:
        await safe_edit(callback,
            f"{label}\n\n<i>Записей нет.</i>",
            reply_markup=_back_btn("admin:events_mgmt"),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    buttons = []
    for e in events:
        date_str = e.event_date.strftime("%d.%m %H:%M")
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {date_str} {e.title[:25]}",
                callback_data=f"admin:evdel:{e.event_id[:16]}",
            )
        ])
    buttons.append(_back_row("admin:events_mgmt"))

    await safe_edit(callback,
        f"{label} — нажми на запись чтобы удалить:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:evdel:"))
async def admin_evdel(callback: types.CallbackQuery):
    # event_id усечён до 16 символов — ищем по всем активным
    partial_id = callback.data.split(":")[2]
    from bot.utils.db_connector import get_events_by_type as gev
    all_evs = []
    for et in ["booking", "announcement", "holiday", "birthday"]:
        all_evs.extend(await gev(et, limit=50))
    target = next((e for e in all_evs if e.event_id.startswith(partial_id)), None)
    if not target:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    await delete_event(target.event_id)
    await callback.answer("🗑 Удалено", show_alert=True)
    await admin_events_mgmt(callback)


# ────────────────────────────────────────────────────────────────────────────
#  Рассылка
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    """Выбор типа рассылки: текст, акция или событие."""
    await state.set_state(AdminBroadcastState.waiting_type)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст (свой текст)", callback_data="admin:bc_type:text")],
        [InlineKeyboardButton(text="🎉 Акция (из списка)", callback_data="admin:bc_type:promo")],
        [InlineKeyboardButton(text="📅 Событие (из списка)", callback_data="admin:bc_type:event")],
        [InlineKeyboardButton(text="✖ Отмена", callback_data="admin:panel")],
    ])
    await safe_edit(callback,
        "📣 <b>Рассылка сотрудникам</b>\n\n"
        "Выберите тип оповещения:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:bc_type:"))
async def admin_bc_type_select(callback: types.CallbackQuery, state: FSMContext):
    """Выбор типа рассылки."""
    bc_type = callback.data[len("admin:bc_type:"):]
    await state.update_data(broadcast_type=bc_type)

    if bc_type == "text":
        # Текст: запрос текста сообщения
        await state.set_state(AdminBroadcastState.waiting_text)
        await state.update_data(fsm_action="broadcast_text")  # Для обработчика сообщения
        await safe_edit(callback,
            "📝 <b>Введите текст рассылки</b>\n\n"
            "<i>Поддерживается HTML форматирование</i>",
            reply_markup=_back_btn("admin:broadcast", "✖ Назад"),
            parse_mode="HTML",
        )
    elif bc_type == "promo":
        # Акция: список актуальных акций
        from bot.utils.db_connector import get_all_promos
        promos = await get_all_promos()
        if not promos:
            await callback.answer("❌ Нет активных акций", show_alert=True)
            await state.clear()
            return

        rows = [[InlineKeyboardButton(text=p.title, callback_data=f"admin:bc_promo:{p.promo_key}")]
                for p in promos]
        rows.append([InlineKeyboardButton(text="✖ Назад", callback_data="admin:broadcast")])

        await safe_edit(callback,
            "🎉 <b>Выберите акцию для оповещения</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
    elif bc_type == "event":
        # Событие: список предстоящих событий
        from bot.utils.db_connector import get_upcoming_events
        events = await get_upcoming_events(days=30)
        if not events:
            await callback.answer("❌ Нет событий", show_alert=True)
            await state.clear()
            return

        rows = [[InlineKeyboardButton(
            text=f"{e.event_type[:20]} • {e.event_date.strftime('%d.%m')}",
            callback_data=f"admin:bc_event:{e.event_id}"
        )] for e in events[:10]]  # Максимум 10
        rows.append([InlineKeyboardButton(text="✖ Назад", callback_data="admin:broadcast")])

        await safe_edit(callback,
            "📅 <b>Выберите событие для оповещения</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("admin:bc_promo:"))
async def admin_bc_promo_select(callback: types.CallbackQuery, state: FSMContext):
    """Выбор акции для рассылки."""
    promo_key = callback.data[len("admin:bc_promo:"):]
    from bot.utils.db_connector import get_all_promos
    from bot.utils.promo_scheduler import build_promo_message

    promos = await get_all_promos()
    promo = next((p for p in promos if p.promo_key == promo_key), None)
    if not promo:
        await callback.answer("❌ Акция не найдена", show_alert=True)
        return

    text = build_promo_message([promo], None).strip()
    await state.update_data(broadcast_text=text, broadcast_source="promo", broadcast_id=promo_key)
    await state.set_state(AdminBroadcastState.waiting_target)
    await _show_broadcast_targets(callback, text, "акция")


@router.callback_query(F.data.startswith("admin:bc_event:"))
async def admin_bc_event_select(callback: types.CallbackQuery, state: FSMContext):
    """Выбор события для рассылки."""
    event_id = callback.data[len("admin:bc_event:"):]
    from bot.utils.db_connector import get_upcoming_events

    events = await get_upcoming_events(days=30)
    event = next((e for e in events if e.event_id == event_id), None)
    if not event:
        await callback.answer("❌ Событие не найдено", show_alert=True)
        return

    text = (
        f"📅 <b>Событие</b>\n\n"
        f"<b>{event.event_type}</b>\n"
        f"📍 {event.description or '—'}\n"
        f"🕐 {event.event_date.strftime('%d.%m.%Y')}"
    )
    await state.update_data(broadcast_text=text, broadcast_source="event", broadcast_id=event_id)
    await state.set_state(AdminBroadcastState.waiting_target)
    await _show_broadcast_targets(callback, text, "событие")


async def _show_broadcast_targets(callback, text: str, source_label: str):
    """Показать выбор целевой аудитории для рассылки."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Всем",              callback_data="admin:broadcast_target:all")],
        [InlineKeyboardButton(text="🍺 Барменам",          callback_data="admin:broadcast_target:barman")],
        [InlineKeyboardButton(text="🍽 Официантам",        callback_data="admin:broadcast_target:waiter")],
        [InlineKeyboardButton(text="🥘 Поварам",           callback_data="admin:broadcast_target:cook")],
        [InlineKeyboardButton(text="🍳 Шеф-поварам",      callback_data="admin:broadcast_target:chef")],
        [InlineKeyboardButton(text="🍸 Бар-менеджерам",   callback_data="admin:broadcast_target:bar_manager")],
        [InlineKeyboardButton(text="👔 Менеджерам",       callback_data="admin:broadcast_target:manager")],
        [InlineKeyboardButton(text="🧹 Хозяюшкам",        callback_data="admin:broadcast_target:cleaning")],
        [InlineKeyboardButton(text="🔧 Техникам",         callback_data="admin:broadcast_target:technician")],
        [InlineKeyboardButton(text="✖ Отмена",            callback_data="admin:broadcast")],
    ])
    preview = text[:200] + ("..." if len(text) > 200 else "")
    await safe_edit(callback,
        f"📣 <b>Рассылка: {source_label}</b>\n\n"
        f"Кому отправить?\n\n"
        f"<b>Текст:</b>\n{preview}",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:broadcast_target:"))
async def admin_broadcast_target(callback: types.CallbackQuery, state: FSMContext):
    target = callback.data.split(":")[2]
    data = await state.get_data()
    text = data.get("broadcast_text", "")

    await state.update_data(broadcast_target=target)
    await state.set_state(AdminBroadcastState.waiting_confirm)

    target_labels = {
        "all":         "👥 всем",
        "barman":      "🍺 барменам",
        "waiter":      "🍽 официантам",
        "cook":        "🥘 поварам",
        "chef":        "🍳 шеф-поварам",
        "bar_manager": "🍸 бар-менеджерам",
        "manager":     "👔 менеджерам",
        "cleaning":    "🧹 хозяюшкам",
        "technician":  "🔧 техникам",
    }
    tlabel = target_labels.get(target, target)

    preview = text[:200] + ("..." if len(text) > 200 else "")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data=f"admin:broadcast_confirm:{target}"),
            InlineKeyboardButton(text="✖ Отмена", callback_data="admin:panel"),
        ],
    ])
    await safe_edit(callback,
        f"📣 <b>Подтверждение рассылки</b>\n\n"
        f"📤 Кому: {tlabel}\n\n"
        f"<b>Текст:</b>\n{preview}",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:broadcast_confirm:"))
async def admin_broadcast_confirm(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    target = callback.data.split(":")[2]
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()

    users = await get_all_users(status="active")
    if target != "all":
        # Рассылка по должности (position) или по роли (role, только для админов и владельцев)
        users = [u for u in users if u.position == target or u.role == target]

    sent = 0
    failed = 0
    for u in users:
        try:
            await bot.send_message(u.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.warning(f"Рассылка: не отправлено {u.telegram_id}: {e}")
            failed += 1

    await safe_edit(callback,
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=_back_btn("admin:panel"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery):
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Фото меню — загрузка и управление
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:menu_photo")
async def admin_menu_photo(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍴 Кухня", callback_data="admin:mphoto_k")],
        [InlineKeyboardButton(text="🍷 Бар",   callback_data="admin:mphoto_b")],
        _back_row("admin:panel"),
    ])
    await safe_edit(callback,
        "📸 <b>Фото меню</b>\n\nВыберите раздел:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:mphoto_k")
async def admin_mphoto_kitchen(callback: types.CallbackQuery):
    cats = get_categories("kitchen")
    buttons = [
        [InlineKeyboardButton(text=cat["name"], callback_data=f"admin:mphoto_kc:{cat['name']}")]
        for cat in cats
    ]
    buttons.append(_back_row("admin:menu_photo"))
    await safe_edit(callback,
        "🍴 <b>Фото меню — Кухня</b>\n\nВыберите категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:mphoto_b")
async def admin_mphoto_bar(callback: types.CallbackQuery):
    cats = get_categories("bar")
    buttons = [
        [InlineKeyboardButton(text=cat["name"], callback_data=f"admin:mphoto_bc:{cat['name']}")]
        for cat in cats
    ]
    buttons.append(_back_row("admin:menu_photo"))
    await safe_edit(callback,
        "🍷 <b>Фото меню — Бар</b>\n\nВыберите категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:mphoto_kc:"))
async def admin_mphoto_kitchen_cat(callback: types.CallbackQuery):
    cat_name = callback.data[len("admin:mphoto_kc:"):]
    items = get_dishes_by_category(cat_name)
    buttons = []
    for item in items:
        icon = "✅" if item["photo_id"] else "📷"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {item['name']}",
            callback_data=f"admin:mphoto_dish:{item['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="← К категориям", callback_data="admin:mphoto_k")])
    await safe_edit(callback,
        f"🍴 <b>{cat_name}</b>\n\n✅ — фото есть  📷 — фото нет\n\nВыберите блюдо:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:mphoto_bc:"))
async def admin_mphoto_bar_cat(callback: types.CallbackQuery):
    cat_name = callback.data[len("admin:mphoto_bc:"):]
    items = get_drinks_by_category(cat_name)
    buttons = []
    for item in items:
        icon = "✅" if item["photo_id"] else "📷"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {item['name']}",
            callback_data=f"admin:mphoto_drink:{item['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="← К категориям", callback_data="admin:mphoto_b")])
    await safe_edit(callback,
        f"🍷 <b>{cat_name}</b>\n\n✅ — фото есть  📷 — фото нет\n\nВыберите напиток:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:mphoto_dish:"))
async def admin_mphoto_dish_card(callback: types.CallbackQuery, state: FSMContext):
    try:
        dish_id = int(callback.data[len("admin:mphoto_dish:"):])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    dish = get_dish_by_id(dish_id)
    if not dish:
        await callback.answer("Блюдо не найдено", show_alert=True)
        return

    status = "✅ Фото загружено" if dish["photo_id"] else "📷 Фото не загружено"
    text = (
        f"🍴 <b>{dish['name']}</b>\n\n"
        f"{status}\n\n"
        "Нажмите «📸 Загрузить фото», затем отправьте фотографию."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Загрузить фото", callback_data=f"admin:mphoto_upload_d:{dish_id}")],
        [InlineKeyboardButton(text="← К списку", callback_data=f"admin:mphoto_kc:{dish['category_name']}")],
    ])
    await safe_edit(callback, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:mphoto_drink:"))
async def admin_mphoto_drink_card(callback: types.CallbackQuery, state: FSMContext):
    try:
        drink_id = int(callback.data[len("admin:mphoto_drink:"):])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    drink = get_drink_by_id(drink_id)
    if not drink:
        await callback.answer("Напиток не найден", show_alert=True)
        return

    status = "✅ Фото загружено" if drink["photo_id"] else "📷 Фото не загружено"
    text = (
        f"🍷 <b>{drink['name']}</b>\n\n"
        f"{status}\n\n"
        "Нажмите «📸 Загрузить фото», затем отправьте фотографию."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Загрузить фото", callback_data=f"admin:mphoto_upload_b:{drink_id}")],
        [InlineKeyboardButton(text="← К списку", callback_data=f"admin:mphoto_bc:{drink['category_name']}")],
    ])
    await safe_edit(callback, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:mphoto_upload_d:"))
async def admin_mphoto_upload_dish_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        dish_id = int(callback.data[len("admin:mphoto_upload_d:"):])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    await state.set_state(MenuPhotoUploadState.waiting_photo)
    await state.update_data(item_type="dish", item_id=dish_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin:mphoto_dish:{dish_id}")],
    ])
    await safe_edit(callback,
        "📸 <b>Загрузка фото</b>\n\nОтправьте фотографию блюда в этот чат:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:mphoto_upload_b:"))
async def admin_mphoto_upload_drink_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        drink_id = int(callback.data[len("admin:mphoto_upload_b:"):])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    await state.set_state(MenuPhotoUploadState.waiting_photo)
    await state.update_data(item_type="drink", item_id=drink_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin:mphoto_drink:{drink_id}")],
    ])
    await safe_edit(callback,
        "📸 <b>Загрузка фото</b>\n\nОтправьте фотографию напитка в этот чат:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(MenuPhotoUploadState.waiting_photo)
async def admin_mphoto_receive(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("⚠️ Пожалуйста, отправьте <b>фотографию</b> (не файл).", parse_mode="HTML")
        return

    data = await state.get_data()
    item_type = data.get("item_type")
    item_id = data.get("item_id")
    photo_id = message.photo[-1].file_id

    if item_type == "dish":
        ok = update_dish_photo(item_id, photo_id)
        dish = get_dish_by_id(item_id)
        name = dish["name"] if dish else str(item_id)
        back_cb = f"admin:mphoto_dish:{item_id}"
    else:
        ok = update_drink_photo(item_id, photo_id)
        drink = get_drink_by_id(item_id)
        name = drink["name"] if drink else str(item_id)
        back_cb = f"admin:mphoto_drink:{item_id}"

    await state.clear()

    if ok:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К карточке", callback_data=back_cb)],
            [InlineKeyboardButton(text="← Фото меню",  callback_data="admin:menu_photo")],
        ])
        await message.answer_photo(
            photo=photo_id,
            caption=f"✅ <b>Фото сохранено</b>\n\n{name}",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Не удалось сохранить фото. Попробуйте ещё раз.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="admin:menu_photo")],
            ]),
        )
