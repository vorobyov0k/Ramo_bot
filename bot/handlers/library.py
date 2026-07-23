"""Обработчик раздела Библиотека — база знаний."""
import logging
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.utils.cache_manager import get_cache_manager
from bot.utils.db_connector import get_user_by_telegram_id
from bot.utils.positions import MANAGER_ROLES
from bot.utils.menu_db import (
    get_dishes_by_category, get_dish_by_id,
    get_drinks_by_category, get_drink_by_id,
)

router = Router()
logger = logging.getLogger(__name__)


def _back_btn(target: str = "menu:library", label: str = "← Назад"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=target)],
    ])


def _back_row(target: str = "menu:library", label: str = "← Назад"):
    return [InlineKeyboardButton(text=label, callback_data=target)]


async def _edit_or_resend(message: types.Message, text: str, keyboard: InlineKeyboardMarkup) -> None:
    """Редактирует текст сообщения или пересылает как новое (если это фото-сообщение)."""
    try:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest:
        await message.delete()
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ────────────────────────────────────────────────────────────────────────────
#  Главное меню библиотеки
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:library")
async def library_menu(callback: types.CallbackQuery):
    text = "📚 <b>Библиотека RAMO</b>\n\nВыберите раздел:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Чек-листы смен",          callback_data="lib:checklists")],
        [InlineKeyboardButton(text="👔 Должности и обязанности",  callback_data="lib:roles")],
        [InlineKeyboardButton(text="📜 Регламенты",              callback_data="lib:regulations")],
        [InlineKeyboardButton(text="❓ FAQ",                     callback_data="lib:faq")],
        [InlineKeyboardButton(text="🍴 Меню кухни",              callback_data="lib:kitchen")],
        [InlineKeyboardButton(text="🍷 Меню бара",               callback_data="lib:bar")],
        [InlineKeyboardButton(text="☎️ Контакты",                callback_data="lib:contacts")],
        [InlineKeyboardButton(text="← Главное меню",             callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Чек-листы
# ────────────────────────────────────────────────────────────────────────────

# Все доступные чеклисты: ключ → (иконка, название)
_ALL_CHECKLISTS = [
    ("opening",  "🌅 Открытие смены"),
    ("closing",  "🌙 Закрытие смены"),
    ("bar",      "🍸 Чек-лист бармена"),
    ("floor",    "🍽 Чек-лист официанта"),
    ("cleaning", "🧹 Чек-лист клининга"),
    ("kitchen",  "🍳 Чек-лист кухни"),
]

# Какие чеклисты видит работник по роли
_ROLE_CHECKLISTS = {
    "barman":   ["opening", "closing", "bar"],
    "waiter":   ["opening", "closing", "floor"],
    "security": ["opening", "closing"],
    "cleaning": ["opening", "closing", "cleaning"],
    "cook":     ["opening", "closing", "kitchen"],
    "chef":     ["opening", "closing", "kitchen"],
}
_MANAGER_ROLES = MANAGER_ROLES


@router.callback_query(F.data == "lib:checklists")
async def checklists_menu(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    role = user.role if user else None

    # Менеджеры видят все; остальные — только по роли
    if role in _MANAGER_ROLES:
        visible_keys = [k for k, _ in _ALL_CHECKLISTS]
    else:
        visible_keys = _ROLE_CHECKLISTS.get(role, ["opening", "closing"])

    cl_map = {k: label for k, label in _ALL_CHECKLISTS}

    rows = []
    for key in visible_keys:
        label = cl_map.get(key, key)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"lib:cl:{key}")])
    rows.append(_back_row())

    text = "✅ <b>Чек-листы</b>\n\nВыберите список:"
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lib:cl:"))
async def checklist_view(callback: types.CallbackQuery):
    """Универсальный просмотр любого чеклиста по ключу."""
    key = callback.data[len("lib:cl:"):]
    cache = get_cache_manager()
    cl_data = cache.get("checklists")
    if not cl_data or key not in cl_data:
        await callback.answer("📭 Чек-лист не найден", show_alert=True)
        return

    cl = cl_data[key]
    items = cl.get("items", [])
    title = cl.get("title", key)
    desc = cl.get("description", "")

    lines = [f"<b>{title}</b>"]
    if desc:
        lines.append(f"<i>{desc}</i>")
    lines.append("")

    current_zone = None
    for item in items:
        zone = item.get("zone", "")
        if zone and zone != current_zone:
            current_zone = zone
            lines.append(f"\n<b>📍 {zone}</b>")
        lines.append(f"☐ {item['text']}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n<i>…</i>"

    await callback.message.edit_text(
        text,
        reply_markup=_back_btn("lib:checklists", "← К чек-листам"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Роли и обязанности
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "lib:roles")
async def roles_menu(callback: types.CallbackQuery):
    text = "👔 <b>Должности и обязанности</b>\n\nВыберите должность:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍺 Бармен",           callback_data="lib:role_barman"),
            InlineKeyboardButton(text="🍽 Официант",          callback_data="lib:role_waiter"),
        ],
        [
            InlineKeyboardButton(text="🥘 Повар",             callback_data="lib:role_cook"),
            InlineKeyboardButton(text="🔪 Су-шеф",           callback_data="lib:role_sous_chef"),
        ],
        [
            InlineKeyboardButton(text="🍸 Бар-менеджер",     callback_data="lib:role_bar_manager"),
            InlineKeyboardButton(text="🍳 Шеф-повар",        callback_data="lib:role_chef"),
        ],
        [
            InlineKeyboardButton(text="🧹 Хозяюшка",         callback_data="lib:role_cleaning"),
            InlineKeyboardButton(text="🔧 Техник",            callback_data="lib:role_technician"),
        ],
        [
            InlineKeyboardButton(text="👑 Собственник",       callback_data="lib:role_owner"),
            InlineKeyboardButton(text="📊 Проект. менеджер", callback_data="lib:role_pm"),
        ],
        _back_row(),
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


_ROLE_SECTION_LABELS = {
    "info":      "📌 Общая информация",
    "zones":     "🗺 Зона ответственности",
    "kpi":       "🎯 KPI",
    "forbidden": "🚫 Запрещено",
    "rules":     "📋 Ключевые правила",
}
_ROLE_SECTION_ORDER = ["info", "kpi", "forbidden", "rules", "zones"]


@router.callback_query(F.data.startswith("lib:role_"))
async def role_detail(callback: types.CallbackQuery):
    data = callback.data[len("lib:role_"):]
    cache = get_cache_manager()
    roles = cache.get("positions")
    if not roles:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    # Подраздел роли: lib:role_{role_key}_s_{section_id}
    if "_s_" in data:
        role_key, section_id = data.split("_s_", 1)
        role = roles.get(role_key)
        if not role:
            await callback.answer("Должность не найдена", show_alert=True)
            return
        sections = role.get("sections", {})
        content = sections.get(section_id)
        if not content:
            content = "<i>Раздел в разработке.</i>"
        await callback.message.edit_text(
            content,
            reply_markup=_back_btn(f"lib:role_{role_key}", "← К разделам должности"),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Главная карточка роли — 5 кнопок разделов
    role_key = data
    role = roles.get(role_key)
    if not role:
        await callback.answer("Должность не найдена", show_alert=True)
        return

    title = role.get("title", role_key)
    sections = role.get("sections", {})

    buttons = []
    # Показываем кнопки в заданном порядке, попарно
    available = [s for s in _ROLE_SECTION_ORDER if s in sections or True]
    row = []
    for sec_id in _ROLE_SECTION_ORDER:
        label = _ROLE_SECTION_LABELS[sec_id]
        btn = InlineKeyboardButton(text=label, callback_data=f"lib:role_{role_key}_s_{sec_id}")
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Кнопка инструкции по смене (если есть)
    ji = cache.get("job_instructions") or {}
    if ji.get(role_key):
        buttons.append([InlineKeyboardButton(
            text="📋 Инструкция по смене",
            callback_data=f"lib:jobi_{role_key}",
        )])

    buttons.append(_back_row("lib:roles", "← К списку должностей"))

    await callback.message.edit_text(
        f"👔 <b>{title}</b>\n\nВыберите раздел:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Должностные инструкции (детальные чек-листы по должности)
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("lib:jobi_"))
async def job_instruction_detail(callback: types.CallbackQuery):
    role_key = callback.data[len("lib:jobi_"):]
    cache = get_cache_manager()
    ji = cache.get("job_instructions")
    if not ji:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    role = ji.get(role_key)
    if not role:
        await callback.answer("Инструкция не найдена", show_alert=True)
        return

    title = role.get("title", "Инструкция")
    lines = [f"<b>{title}</b>"]

    for section_key, header in [
        ("opening_checklist", "🌅 Открытие"),
        ("shift_duties", "🔄 В течение смены"),
        ("closing_checklist", "🌙 Закрытие"),
    ]:
        items = role.get(section_key, [])
        if not items:
            continue
        lines.append(f"\n<b>{header}:</b>")
        for item in items:
            lines.append(f"  ☐ {item}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."

    await callback.message.edit_text(
        text,
        reply_markup=_back_btn(f"lib:role_{role_key}", "← К описанию должности"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Регламенты — по категориям
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "lib:regulations")
async def regulations_menu(callback: types.CallbackQuery):
    cache = get_cache_manager()
    regs = cache.get("regulations")
    if not regs:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    categories = regs.get("categories", [])
    buttons = [
        [InlineKeyboardButton(text=cat["name"], callback_data=f"lib:regcat_{cat['id']}")]
        for cat in categories
    ]
    buttons.append(_back_row())

    await callback.message.edit_text(
        "📜 <b>Регламенты RAMO</b>\n\nВыберите категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lib:regcat_"))
async def regulations_category(callback: types.CallbackQuery):
    cat_id = callback.data[len("lib:regcat_"):]
    cache = get_cache_manager()
    regs = cache.get("regulations")
    if not regs:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    categories = regs.get("categories", [])
    cat = next((c for c in categories if c["id"] == cat_id), None)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    sections = [s for s in regs.get("sections", []) if s.get("cat") == cat_id]
    buttons = [
        [InlineKeyboardButton(text=s["name"], callback_data=f"lib:reg_{s['id']}")]
        for s in sections
    ]
    buttons.append([InlineKeyboardButton(text="← К категориям", callback_data="lib:regulations")])

    await callback.message.edit_text(
        f"📜 <b>{cat['name']}</b>\n\nВыберите раздел:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lib:reg_"))
async def regulation_detail(callback: types.CallbackQuery):
    data = callback.data[len("lib:reg_"):]

    # Подраздел: lib:reg_{section_id}_s_{sub_id}
    if "_s_" in data:
        section_id, sub_id = data.split("_s_", 1)
        cache = get_cache_manager()
        regs = cache.get("regulations")
        if not regs:
            await callback.answer("📭 Данные не найдены", show_alert=True)
            return
        section = next((s for s in regs.get("sections", []) if s["id"] == section_id), None)
        if not section:
            await callback.answer("Раздел не найден", show_alert=True)
            return
        sub = next((s for s in section.get("subsections", []) if s["id"] == sub_id), None)
        if not sub:
            await callback.answer("Подраздел не найден", show_alert=True)
            return
        await callback.message.edit_text(
            sub["content"],
            reply_markup=_back_btn(f"lib:reg_{section_id}", "← К разделам"),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Обычный регламент или регламент с подразделами
    section_id = data
    cache = get_cache_manager()
    regs = cache.get("regulations")
    if not regs:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    section = next(
        (s for s in regs.get("sections", []) if s["id"] == section_id), None
    )
    if not section:
        await callback.answer("Раздел не найден", show_alert=True)
        return

    cat_id = section.get("cat", "")
    back_target = f"lib:regcat_{cat_id}" if cat_id else "lib:regulations"

    # Если есть подразделы — показываем список кнопок
    if section.get("subsections"):
        buttons = [
            [InlineKeyboardButton(text=sub["name"], callback_data=f"lib:reg_{section_id}_s_{sub['id']}")]
            for sub in section["subsections"]
        ]
        buttons.append([InlineKeyboardButton(text="← К списку", callback_data=back_target)])
        await callback.message.edit_text(
            f"📄 <b>{section['name']}</b>\n\nВыберите раздел:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        section["content"],
        reply_markup=_back_btn(back_target, "← К списку"),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  FAQ
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "lib:faq")
async def faq_handler(callback: types.CallbackQuery):
    cache = get_cache_manager()
    faq = cache.get("faq")
    if not faq:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    items = faq.get("items", [])
    rows = []
    for i, item in enumerate(items):
        q_short = item["q"][:55] + ("…" if len(item["q"]) > 55 else "")
        rows.append([InlineKeyboardButton(
            text=f"❓ {q_short}",
            callback_data=f"lib:faq:{i}",
        )])
    rows.append(_back_row())

    await callback.message.edit_text(
        f"❓ <b>FAQ — Часто задаваемые вопросы</b>\n\n"
        f"Выбери вопрос — увидишь ответ:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lib:faq:"))
async def faq_item_handler(callback: types.CallbackQuery):
    raw = callback.data[len("lib:faq:"):]
    try:
        idx = int(raw)
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    cache = get_cache_manager()
    faq = cache.get("faq")
    if not faq:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    items = faq.get("items", [])
    if idx < 0 or idx >= len(items):
        await callback.answer("Вопрос не найден", show_alert=True)
        return

    item = items[idx]
    total = len(items)

    nav_row = []
    if idx > 0:
        nav_row.append(InlineKeyboardButton(text="← Пред.", callback_data=f"lib:faq:{idx - 1}"))
    if idx < total - 1:
        nav_row.append(InlineKeyboardButton(text="След. →", callback_data=f"lib:faq:{idx + 1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        *([nav_row] if nav_row else []),
        [InlineKeyboardButton(text="← К списку вопросов", callback_data="lib:faq")],
    ])

    text = (
        f"❓ <b>{item['q']}</b>\n\n"
        f"💬 {item['a']}\n\n"
        f"<i>{idx + 1} / {total}</i>"
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Контакты
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "lib:contacts")
async def contacts_handler(callback: types.CallbackQuery):
    cache = get_cache_manager()
    contacts = cache.get("contacts")
    if not contacts:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    lines = ["☎️ <b>Контакты RAMO</b>\n"]
    for item in contacts.get("items", []):
        lines.append(f"{item['name']}")
        lines.append(f"<code>{item['phone']}</code>  <i>({item['role']})</i>")
        lines.append("")

    if note := contacts.get("note"):
        lines.append(f"ℹ️ <i>{note}</i>")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_btn(),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Меню из БД (кухня и бар) — разделены по категориям
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "lib:kitchen")
async def kitchen_menu_categories(callback: types.CallbackQuery):
    """Категории меню кухни."""
    from bot.utils.menu_db import get_categories
    cats = get_categories("kitchen")
    if not cats:
        await callback.answer("Меню кухни не найдено", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text=cat["name"], callback_data=f"lib:kitchen_cat:{cat['name']}")]
        for cat in cats
    ]
    buttons.append(_back_row())

    await _edit_or_resend(
        callback.message,
        "🍴 <b>Меню кухни</b>\n\nВыберите категорию:",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lib:kitchen_cat:"))
async def kitchen_category(callback: types.CallbackQuery):
    """Блюда в категории — отображаются как кнопки."""
    category = callback.data[len("lib:kitchen_cat:"):]
    items = get_dishes_by_category(category)
    if not items:
        await callback.answer("Нет блюд в этой категории", show_alert=True)
        return

    buttons = []
    for item in items:
        tags = []
        if item["is_spicy"]:     tags.append("🌶️")
        if item["is_vegetarian"]: tags.append("🥗")
        if item["is_new"]:       tags.append("✨")
        if item["is_healthy"]:   tags.append("💪")
        tag_str = " ".join(tags)
        price_str = f" {item['price']} ₽" if item["price"] else ""
        label = f"{item['name']}{price_str} {tag_str}".strip()
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"lib:dish:{item['id']}")])

    buttons.append([InlineKeyboardButton(text="← К категориям", callback_data="lib:kitchen")])

    await _edit_or_resend(
        callback.message,
        f"🍴 <b>{category}</b>\n\nВыберите блюдо:",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lib:dish:"))
async def dish_detail(callback: types.CallbackQuery):
    """Карточка блюда с фото (если есть)."""
    try:
        dish_id = int(callback.data[len("lib:dish:"):])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    dish = get_dish_by_id(dish_id)
    if not dish:
        await callback.answer("Блюдо не найдено", show_alert=True)
        return

    tags = []
    if dish["is_spicy"]:     tags.append("🌶️ Острое")
    if dish["is_vegetarian"]: tags.append("🥗 Веган")
    if dish["is_new"]:       tags.append("✨ Новинка")
    if dish["is_healthy"]:   tags.append("💪 ПП")

    text = f"🍴 <b>{dish['name']}</b>\n"
    if dish["price"]:
        text += f"💰 {dish['price']} ₽\n"
    if tags:
        text += "🏷 " + "  ".join(tags) + "\n"
    if dish["description"]:
        text += f"\n{dish['description']}"

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← К категории", callback_data=f"lib:kitchen_cat:{dish['category_name']}")],
    ])

    if dish["photo_id"]:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer_photo(
            photo=dish["photo_id"],
            caption=text,
            reply_markup=back_kb,
            parse_mode="HTML",
        )
    else:
        await _edit_or_resend(callback.message, text, back_kb)

    await callback.answer()


@router.callback_query(F.data == "lib:bar")
async def bar_menu_categories(callback: types.CallbackQuery):
    """Категории меню бара."""
    from bot.utils.menu_db import get_categories
    cats = get_categories("bar")
    if not cats:
        await callback.answer("Меню бара не найдено", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text=cat["name"], callback_data=f"lib:bar_cat:{cat['name']}")]
        for cat in cats
    ]
    buttons.append(_back_row())

    await _edit_or_resend(
        callback.message,
        "🍷 <b>Меню бара</b>\n\nВыберите категорию:",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lib:bar_cat:"))
async def bar_category(callback: types.CallbackQuery):
    """Напитки в категории — отображаются как кнопки."""
    category = callback.data[len("lib:bar_cat:"):]
    items = get_drinks_by_category(category)
    if not items:
        await callback.answer("Нет напитков в этой категории", show_alert=True)
        return

    buttons = []
    for item in items:
        tags = []
        if item["is_non_alcoholic"]: tags.append("☕")
        if item["is_vegetarian"]:    tags.append("🥗")
        if item["is_new"]:           tags.append("✨")
        if item["is_healthy"]:       tags.append("💪")
        tag_str = " ".join(tags)
        price_str = f" {item['price']} ₽" if item["price"] else ""
        label = f"{item['name']}{price_str} {tag_str}".strip()
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"lib:drink:{item['id']}")])

    buttons.append([InlineKeyboardButton(text="← К категориям", callback_data="lib:bar")])

    await _edit_or_resend(
        callback.message,
        f"🍷 <b>{category}</b>\n\nВыберите напиток:",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lib:drink:"))
async def drink_detail(callback: types.CallbackQuery):
    """Карточка напитка с фото (если есть)."""
    try:
        drink_id = int(callback.data[len("lib:drink:"):])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    drink = get_drink_by_id(drink_id)
    if not drink:
        await callback.answer("Напиток не найден", show_alert=True)
        return

    tags = []
    if drink["is_non_alcoholic"]: tags.append("☕ Безалкогольный")
    if drink["is_vegetarian"]:    tags.append("🥗 Веган")
    if drink["is_new"]:           tags.append("✨ Новинка")
    if drink["is_healthy"]:       tags.append("💪 ПП")

    text = f"🍷 <b>{drink['name']}</b>\n"
    if drink["price"]:
        text += f"💰 {drink['price']} ₽\n"
    if tags:
        text += "🏷 " + "  ".join(tags) + "\n"
    if drink["description"]:
        text += f"\n{drink['description']}"

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← К категории", callback_data=f"lib:bar_cat:{drink['category_name']}")],
    ])

    if drink["photo_id"]:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer_photo(
            photo=drink["photo_id"],
            caption=text,
            reply_markup=back_kb,
            parse_mode="HTML",
        )
    else:
        await _edit_or_resend(callback.message, text, back_kb)

    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Простые разделы: стандарты, расписание, события
# ────────────────────────────────────────────────────────────────────────────

_SIMPLE_SECTIONS = {
    "schedule", "events",
}


@router.callback_query(F.data.startswith("lib:"))
async def library_simple_section(callback: types.CallbackQuery):
    """Fallback: простые разделы с content-строкой."""
    section = callback.data[len("lib:"):]

    if section not in _SIMPLE_SECTIONS:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return

    cache = get_cache_manager()
    data = cache.get(section)
    if not data:
        await callback.answer("📭 Данные не найдены", show_alert=True)
        return

    title = data.get("title", "")
    content = data.get("content", "")
    description = data.get("description", "")

    lines = []
    if title:
        lines.append(f"<b>{title}</b>")
    if description:
        lines.append(f"<i>{description}</i>")
    if (title or description) and content:
        lines.append("")
    if content:
        lines.append(content)

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."

    await callback.message.edit_text(
        text,
        reply_markup=_back_btn(),
        parse_mode="HTML",
    )
    await callback.answer()
