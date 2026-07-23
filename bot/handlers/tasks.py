"""
Обработчик Мои задачи — интерактивные чек-листы смены.
Пункты кликабельны: нажал = отметил/снял галочку (как в голосовании).
"""
import logging
from datetime import datetime
from aiogram import Router, Bot, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.utils.cache_manager import get_cache_manager
from bot.utils.db_connector import get_user_by_telegram_id, save_checklist_execution
from bot.utils.positions import get_user_checklists, MANAGER_ROLES

router = Router()
logger = logging.getLogger(__name__)

_CHECKLIST_LABELS = {
    "opening":  "🌅 Открытие смены",
    "closing":  "🌙 Закрытие смены",
    "bar":      "🍸 Чек-лист бармена",
    "floor":    "🍽 Чек-лист официанта",
    "cleaning": "🧹 Чек-лист клининга",
    "kitchen":  "🍳 Чек-лист кухни",
}

# Маркер в callback_data, чтобы отличать toggle-кнопки от остальных
_TOGGLE_PREFIX = "clt:"   # clt:{cl_type}:{item_id}
_SUBMIT_PREFIX = "cls:"   # cls:{cl_type}
_ZONE_SEP_CB   = "noop"   # нажатие на заголовок зоны

# Прогресс чек-листов в памяти: (telegram_id, cl_type) -> set of done item_ids
# Сбрасывается только после submit. Переживает навигацию по меню, не переживает рестарт бота.
_PROGRESS: dict[tuple[int, str], set] = {}


def _prog_get(user_id: int, cl_type: str) -> set:
    return _PROGRESS.get((user_id, cl_type), set())


def _prog_set(user_id: int, cl_type: str, done_ids: set) -> None:
    _PROGRESS[(user_id, cl_type)] = done_ids


def _prog_clear(user_id: int, cl_type: str) -> None:
    _PROGRESS.pop((user_id, cl_type), None)


# ────────────────────────────────────────────────────────────────────────────
#  Построение интерактивной клавиатуры
# ────────────────────────────────────────────────────────────────────────────

def _build_checklist_kb(cl_type: str, items: list, done_ids: set) -> InlineKeyboardMarkup:
    """
    Строит клавиатуру-чек-лист.
    done_ids — множество item['id'] отмеченных как выполненные.
    """
    rows = []
    prev_zone = None

    for item in items:
        zone = item.get("zone", "")
        item_id = item.get("id", item["text"][:10])

        # Заголовок зоны — нажимаемая «пустая» кнопка-разделитель
        if zone and zone != prev_zone:
            prev_zone = zone
            rows.append([InlineKeyboardButton(
                text=f"━━ 📍 {zone} ━━",
                callback_data=_ZONE_SEP_CB,
            )])

        mark = "✅" if item_id in done_ids else "☐"
        short_text = item["text"][:45] + ("…" if len(item["text"]) > 45 else "")
        rows.append([InlineKeyboardButton(
            text=f"{mark} {short_text}",
            callback_data=f"{_TOGGLE_PREFIX}{cl_type}:{item_id}",
        )])

    done_count = len(done_ids)
    total = len(items)

    rows.append([InlineKeyboardButton(
        text=f"📤 Сдать чек-лист ({done_count}/{total} выполнено)",
        callback_data=f"{_SUBMIT_PREFIX}{cl_type}",
    )])
    rows.append([InlineKeyboardButton(text="← К задачам", callback_data="menu:tasks")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _extract_done_ids(markup: InlineKeyboardMarkup, cl_type: str) -> set:
    """Читает текущие отмеченные пункты прямо из кнопок сообщения."""
    done = set()
    prefix = f"{_TOGGLE_PREFIX}{cl_type}:"
    for row in markup.inline_keyboard:
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith(prefix):
                if btn.text.startswith("✅"):
                    item_id = btn.callback_data[len(prefix):]
                    done.add(item_id)
    return done


def _count_total(markup: InlineKeyboardMarkup, cl_type: str) -> int:
    prefix = f"{_TOGGLE_PREFIX}{cl_type}:"
    return sum(
        1
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data and btn.callback_data.startswith(prefix)
    )


def _checklist_header(cl_type: str, done: int, total: int, description: str = "") -> str:
    label = _CHECKLIST_LABELS.get(cl_type, "Чек-лист")
    bar_filled = round(done / total * 10) if total else 0
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    lines = [
        f"<b>{label}</b>",
        f"[{bar}] {done}/{total}",
    ]
    if description:
        lines.append(f"<i>{description}</i>")
    lines.append("\n💡 Нажимай на пункты чтобы отмечать ✅")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
#  Главное меню задач
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:tasks")
async def tasks_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user_by_telegram_id(user_id)
    role = user.role if user else "user"

    _MANAGER_ROLES = MANAGER_ROLES

    hour = datetime.now().hour
    if hour < 14:
        hint = "☀️ Сейчас утро — начни с открытия!"
    elif hour < 20:
        hint = "🌤 Середина дня — всё идёт по плану?"
    else:
        hint = "🌙 Вечер — скоро закрытие, готовь чек-лист!"

    buttons = []

    # Раздел задач — для менеджеров «Управление», для работников «Мои задачи»
    if role in _MANAGER_ROLES:
        buttons.append([InlineKeyboardButton(
            text="📋 Управление задачами",
            callback_data="tm:main",
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text="📋 Мои задачи от руководства",
            callback_data="mt:main",
        )])

    # Чек-листы — по должности (с фолбэком на роль)
    user_checklists = get_user_checklists(user) if user else []

    if user_checklists:
        buttons.append([InlineKeyboardButton(text="━━ 📝 Чек-листы ━━", callback_data="noop")])

    _CL_BUTTONS = {
        "opening":  ("🌅 Открытие",          "task:view:opening"),
        "closing":  ("🌙 Закрытие",           "task:view:closing"),
        "bar":      ("🍸 Бар",               "task:view:bar"),
        "floor":    ("🍽 Зал",               "task:view:floor"),
        "cleaning": ("🧹 Клининг",           "task:view:cleaning"),
        "kitchen":  ("🍳 Кухня",             "task:view:kitchen"),
    }

    # Загружаем размеры чеклистов для индикатора прогресса
    cache = get_cache_manager()
    cl_data = cache.get("checklists") or {}

    def _cl_btn_label(cl_type: str, base_label: str) -> str:
        done = len(_prog_get(user_id, cl_type))
        if done == 0:
            return base_label
        total_items = len(cl_data.get(cl_type, {}).get("items", []))
        return f"{base_label} ({done}/{total_items})"

    # Открытие и закрытие — в одну строку
    row_pair = []
    for cl_type in ["opening", "closing"]:
        if cl_type in user_checklists and cl_type in _CL_BUTTONS:
            base_label, cb = _CL_BUTTONS[cl_type]
            row_pair.append(InlineKeyboardButton(
                text=_cl_btn_label(cl_type, base_label), callback_data=cb,
            ))
    if row_pair:
        buttons.append(row_pair)

    # Подразделения — попарно
    dept_types = [t for t in ["bar", "floor", "cleaning", "kitchen"] if t in user_checklists]
    for i in range(0, len(dept_types), 2):
        row = []
        for cl_type in dept_types[i:i+2]:
            base_label, cb = _CL_BUTTONS[cl_type]
            row.append(InlineKeyboardButton(
                text=_cl_btn_label(cl_type, base_label), callback_data=cb,
            ))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])

    text = (
        f"📋 <b>Задачи и чек-листы</b>\n\n"
        f"{hint}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Открыть интерактивный чек-лист
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("task:view:"))
async def task_view_checklist(callback: types.CallbackQuery):
    cl_type = callback.data[len("task:view:"):]
    cache = get_cache_manager()
    cl_data = cache.get("checklists")

    if not cl_data or cl_type not in cl_data:
        await callback.answer("📭 Чек-лист не найден", show_alert=True)
        return

    checklist = cl_data[cl_type]
    items = checklist.get("items", [])
    description = checklist.get("description", "")

    if not items:
        await callback.answer("Чек-лист пуст", show_alert=True)
        return

    user_id = callback.from_user.id
    done_ids = _prog_get(user_id, cl_type)

    header = _checklist_header(cl_type, len(done_ids), len(items), description)
    kb = _build_checklist_kb(cl_type, items, done_ids=done_ids)

    await callback.message.edit_text(header, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Нажатие на заголовок зоны — игнорируем
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == _ZONE_SEP_CB)
async def noop_handler(callback: types.CallbackQuery):
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────────
#  Toggle пункта чек-листа
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith(_TOGGLE_PREFIX))
async def toggle_item(callback: types.CallbackQuery):
    # clt:{cl_type}:{item_id}
    rest = callback.data[len(_TOGGLE_PREFIX):]
    parts = rest.split(":", 1)
    if len(parts) < 2:
        await callback.answer()
        return
    cl_type, item_id = parts[0], parts[1]

    user_id = callback.from_user.id

    # Читаем прогресс из памяти (не из кнопок — они могут быть устаревшими)
    done_ids = _prog_get(user_id, cl_type).copy()

    # Переключаем пункт
    if item_id in done_ids:
        done_ids.discard(item_id)
        toast = "☐ Снято"
    else:
        done_ids.add(item_id)
        toast = "✅ Отмечено!"

    # Сохраняем обновлённый прогресс
    _prog_set(user_id, cl_type, done_ids)

    # Перестраиваем клавиатуру
    cache = get_cache_manager()
    cl_data = cache.get("checklists")
    checklist = cl_data.get(cl_type, {})
    items = checklist.get("items", [])
    description = checklist.get("description", "")

    header = _checklist_header(cl_type, len(done_ids), len(items), description)
    new_kb = _build_checklist_kb(cl_type, items, done_ids)

    await callback.message.edit_text(header, reply_markup=new_kb, parse_mode="HTML")
    await callback.answer(toast)


# ────────────────────────────────────────────────────────────────────────────
#  Сдать чек-лист — сохранение в БД
# ────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith(_SUBMIT_PREFIX))
async def submit_checklist(callback: types.CallbackQuery):
    cl_type = callback.data[len(_SUBMIT_PREFIX):]
    user_id = callback.from_user.id
    label = _CHECKLIST_LABELS.get(cl_type, cl_type)

    # Берём прогресс из памяти — он актуален независимо от состояния сообщения
    done_ids = _prog_get(user_id, cl_type)

    # Считаем total из кэша (не из кнопок)
    cache_pre = get_cache_manager()
    cl_data_pre = cache_pre.get("checklists") or {}
    total = len(cl_data_pre.get(cl_type, {}).get("items", []))

    try:
        shift_id = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        execution_id = await save_checklist_execution(
            checklist_type=cl_type,
            user_id=user_id,
            shift_id=shift_id,
            items=[{"item_id": iid, "completed": True} for iid in done_ids],
        )

        done_count = len(done_ids)
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

        # Сбрасываем прогресс — чек-лист сдан
        _prog_clear(user_id, cl_type)

        if done_count == total:
            status_line = "🎉 Все пункты выполнены!"
        else:
            status_line = f"⚠️ Выполнено {done_count} из {total} пунктов"

        text = (
            f"✅ <b>Чек-лист сдан!</b>\n\n"
            f"📋 {label}\n"
            f"{status_line}\n"
            f"⏰ {now_str}\n"
            f"🔖 ID: <code>{execution_id[:8]}…</code>"
        )

        # При закрытии смены — автопередача незакрытых задач
        if cl_type == "closing":
            try:
                from bot.handlers.task_manager import transfer_open_tasks_on_shift_close
                bot: Bot = callback.bot
                transferred = await transfer_open_tasks_on_shift_close(user_id, bot)
                if transferred:
                    text += f"\n\n🔄 Передано задач следующей смене: <b>{transferred}</b>"
            except Exception as te:
                logger.warning(f"Ошибка автопередачи задач: {te}")

    except Exception as e:
        logger.error(f"Ошибка сохранения чек-листа: {e}")
        text = (
            "⚠️ <b>Не удалось сохранить в журнал</b>\n\n"
            "Сообщи менеджеру — он внесёт вручную."
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← К задачам", callback_data="menu:tasks")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer("✅ Записано!")
