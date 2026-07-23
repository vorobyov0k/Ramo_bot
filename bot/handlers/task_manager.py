"""
Модуль управления задачами RAMO.

Роли:
  admin, manager, pm — создают/просматривают/редактируют задачи
  barman, waiter, security — видят свои задачи, выполняют, самофиксируют

Callback prefixes:
  tm:   — Task Manager (менеджер): навигация и действия
  tmc:  — Task Manager Create: FSM кнопки при создании
  tme:  — Task Manager Edit: действия в детали задачи
  mt:   — My Tasks (работник): навигация
  mtc:  — My Tasks Complete: FSM кнопки при выполнении
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo

from aiogram import Router, Bot, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.utils.db_connector import (
    get_user_by_telegram_id,
    get_active_workers,
    create_task,
    get_task,
    get_tasks,
    get_tasks_for_worker,
    complete_task_db,
    reassign_task_db,
    cancel_task_db,
    add_task_comment_db,
    update_task_priority,
    update_task_deadline,
)
from bot.utils.positions import get_position_display, MANAGER_ROLES
from bot.states.forms import (
    TaskCreateState,
    TaskCompleteState,
    TaskSelfLogState,
    TaskCommentState,
    TaskReassignState,
)

router = Router()
logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
UTC = ZoneInfo("UTC")

_MANAGER_ROLES = MANAGER_ROLES
_WORKER_ROLES  = {"barman", "waiter", "security"}

_PRIORITY_LABELS = {
    "urgent": "🔴 Срочно",
    "normal": "🟡 Нормально",
    "low":    "🟢 Низкий",
}
_DEPT_LABELS = {
    "bar":        "🍸 Бар",
    "restaurant": "🍽 Зал",
    "security":   "🛡 Охрана",
    "all":        "🌐 Все отделы",
}
_DEPT_TO_ROLES = {
    "bar": ["barman"],
    "restaurant": ["waiter"],
    "security": ["security"],
    "all": ["barman", "waiter", "security"],
}

TASKS_PER_PAGE = 5


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def _eff_status(task) -> str:
    """Эффективный статус с учётом просрочки."""
    if task.status != "open":
        return task.status
    if task.deadline and task.deadline < datetime.utcnow():
        return "overdue"
    return "open"


def _status_icon(eff_status: str) -> str:
    return {"open": "🟠", "overdue": "⏰", "done": "✅", "cancelled": "🚫"}.get(eff_status, "❓")


def _fmt_dl(dt: Optional[datetime]) -> str:
    if not dt:
        return "без дедлайна"
    msk = dt.replace(tzinfo=UTC).astimezone(MSK)
    return msk.strftime("%d.%m %H:%M")


def _fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    msk = dt.replace(tzinfo=UTC).astimezone(MSK)
    return msk.strftime("%d.%m.%Y %H:%M")


def _now_msk() -> datetime:
    return datetime.now(MSK)


def _deadline_shift_today() -> datetime:
    """Конец смены сегодня 22:00 МСК → UTC."""
    msk_now = _now_msk()
    target = msk_now.replace(hour=22, minute=0, second=0, microsecond=0)
    if target <= msk_now:
        target += timedelta(days=1)
    return target.astimezone(UTC).replace(tzinfo=None)


def _deadline_tomorrow_morning() -> datetime:
    """Завтра 10:00 МСК → UTC."""
    msk_now = _now_msk()
    target = (msk_now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    return target.astimezone(UTC).replace(tzinfo=None)


def _parse_deadline_text(text: str) -> Optional[datetime]:
    """Парсит 'ДД.ММ ЧЧ:ММ' или 'ДД.ММ.ГГ ЧЧ:ММ' → UTC datetime."""
    text = text.strip()
    formats = ["%d.%m %H:%M", "%d.%m.%y %H:%M", "%d.%m.%Y %H:%M"]
    now = _now_msk()
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt == "%d.%m %H:%M":
                dt = dt.replace(year=now.year)
            # Если дата в прошлом — берём следующий год
            dt_msk = dt.replace(tzinfo=MSK)
            if dt_msk < now:
                dt_msk = dt_msk.replace(year=dt_msk.year + 1)
            return dt_msk.astimezone(UTC).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _task_summary_text(data: dict) -> str:
    """Текст-сводка для подтверждения перед созданием задачи."""
    dept = data.get("department")
    assignee = data.get("assigned_to_name") or (
        _DEPT_LABELS.get(dept, dept) if dept else "—"
    )
    dl = data.get("deadline_dt")
    dl_str = _fmt_dl(dl) if dl else "без дедлайна"

    lines = [
        "📋 <b>Новая задача — проверь и подтверди:</b>\n",
        f"<b>Название:</b> {data.get('title', '—')}",
        f"<b>Описание:</b> {data.get('description') or '—'}",
        f"<b>Кому:</b> {assignee}",
        f"<b>Приоритет:</b> {_PRIORITY_LABELS.get(data.get('priority', 'normal'), '—')}",
        f"<b>Дедлайн:</b> {dl_str}",
        f"<b>Фото:</b> {'прикреплено' if data.get('photo_urls') else 'нет'}",
    ]
    return "\n".join(lines)


def _kb_back_to_manager_list():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Список задач", callback_data="tm:list:all:all:0")],
        [InlineKeyboardButton(text="← Главное меню",  callback_data="menu:main")],
    ])


# ─── ТОЧКА ВХОДА В РАЗДЕЛ ────────────────────────────────────────────────────

@router.callback_query(F.data == "tm:main")
async def tm_dashboard(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user_by_telegram_id(user_id)
    if not user or user.role not in _MANAGER_ROLES:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    all_tasks = await get_tasks(limit=500)
    open_tasks = [t for t in all_tasks if _eff_status(t) == "open"]
    overdue_tasks = [t for t in all_tasks if _eff_status(t) == "overdue"]
    done_today = [
        t for t in all_tasks
        if t.status == "done" and t.completed_at
        and t.completed_at.date() == datetime.utcnow().date()
    ]

    text = (
        "📋 <b>Управление задачами</b>\n\n"
        f"🟠 Открытых: <b>{len(open_tasks)}</b>\n"
        f"⏰ Просроченных: <b>{len(overdue_tasks)}</b>\n"
        f"✅ Выполнено сегодня: <b>{len(done_today)}</b>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Новая задача",       callback_data="tm:new")],
        [InlineKeyboardButton(text="🟠 Открытые",           callback_data="tm:list:open:all:0"),
         InlineKeyboardButton(text="⏰ Просроченные",        callback_data="tm:list:overdue:all:0")],
        [InlineKeyboardButton(text="✅ Выполненные",        callback_data="tm:list:done:all:0"),
         InlineKeyboardButton(text="📂 Все задачи",         callback_data="tm:list:all:all:0")],
        [InlineKeyboardButton(text="📊 Журнал задач",      callback_data="tm:journal")],
        [InlineKeyboardButton(text="← Главное меню",        callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "tm:journal")
async def tm_journal(callback: types.CallbackQuery):
    """Журнал всех задач (для pm/admin - все, для исполнителей - только свои)."""
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    all_tasks = await get_tasks(limit=500)

    # Фильтруем задачи в зависимости от роли
    if user.role in MANAGER_ROLES:
        # Менеджеры/админы/владельцы видят все задачи
        tasks = all_tasks
    else:
        # Исполнители видят только свои
        tasks = [t for t in all_tasks if t.assigned_to == user.telegram_id]

    # Группируем по статусам
    done = [t for t in tasks if t.status == "done"]
    cancelled = [t for t in tasks if t.status == "cancelled"]
    open_tasks = [t for t in tasks if t.status == "open"]

    lines = ["📊 <b>Журнал задач</b>\n"]

    if user.role not in {"pm", "admin"}:
        lines.append(f"<i>Ваши задачи:</i>\n")

    lines.append(f"✅ Выполнено: <b>{len(done)}</b>")
    lines.append(f"🚫 Отменено: <b>{len(cancelled)}</b>")
    lines.append(f"🟠 Открыто: <b>{len(open_tasks)}</b>")
    lines.append(f"📊 Всего: <b>{len(tasks)}</b>\n")

    if done:
        lines.append("<b>✅ Выполненные (последние 5):</b>")
        for t in sorted(done, key=lambda x: x.completed_at or datetime.min, reverse=True)[:5]:
            completed_text = _fmt_dt(t.completed_at) if t.completed_at else "—"
            lines.append(f"  • {t.title} ({completed_text})")
        lines.append("")

    if cancelled:
        lines.append("<b>🚫 Отменённые (последние 5):</b>")
        for t in sorted(cancelled, key=lambda x: x.updated_at or datetime.min, reverse=True)[:5]:
            lines.append(f"  • {t.title}")
        lines.append("")

    if open_tasks:
        lines.append("<b>🟠 Открытые:</b>")
        for t in sorted(open_tasks, key=lambda x: x.deadline or datetime.max)[:5]:
            dl_text = _fmt_dl(t.deadline)
            lines.append(f"  • {t.title} — {dl_text}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Управление задачами", callback_data="tm:main")],
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


# ─── СОЗДАНИЕ ЗАДАЧИ: FSM ────────────────────────────────────────────────────

@router.callback_query(F.data == "tm:new")
async def tm_new_task(callback: types.CallbackQuery, state: FSMContext):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.role not in _MANAGER_ROLES:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await state.clear()
    await state.set_state(TaskCreateState.waiting_title)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖ Отмена", callback_data="tmc:cancel")],
    ])
    await callback.message.edit_text(
        "✏️ <b>Создание задачи — шаг 1/6</b>\n\n"
        "Введите <b>название задачи</b>:",
        reply_markup=kb, parse_mode="HTML",
    )
    await callback.answer()


@router.message(TaskCreateState.waiting_title)
async def tc_got_title(message: types.Message, state: FSMContext):
    title = message.text.strip() if message.text else ""
    if not title:
        await message.answer("⚠️ Название не может быть пустым. Введите ещё раз:")
        return
    await state.update_data(title=title)
    await state.set_state(TaskCreateState.waiting_description)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="tmc:skip_desc")],
        [InlineKeyboardButton(text="✖ Отмена",     callback_data="tmc:cancel")],
    ])
    await message.answer(
        f"✅ Название: <b>{title}</b>\n\n"
        "📝 <b>Шаг 2/6.</b> Введите <b>описание</b> задачи (или пропустите):",
        reply_markup=kb, parse_mode="HTML",
    )


@router.callback_query(F.data == "tmc:skip_desc", TaskCreateState.waiting_description)
async def tc_skip_desc(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(description=None)
    await _ask_assignee(callback.message, state, edit=True)
    await callback.answer()


@router.message(TaskCreateState.waiting_description)
async def tc_got_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip() if message.text else None)
    await _ask_assignee(message, state, edit=False)


async def _ask_assignee(message_or_obj, state: FSMContext, edit: bool = False):
    await state.set_state(TaskCreateState.waiting_dept)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍸 Бар",         callback_data="tmc:dept:bar"),
         InlineKeyboardButton(text="🍽 Зал",          callback_data="tmc:dept:restaurant")],
        [InlineKeyboardButton(text="🛡 Охрана",       callback_data="tmc:dept:security"),
         InlineKeyboardButton(text="🌐 Все отделы",   callback_data="tmc:dept:all")],
        [InlineKeyboardButton(text="👤 Конкретный сотрудник", callback_data="tmc:dept:pick_user")],
        [InlineKeyboardButton(text="✖ Отмена",        callback_data="tmc:cancel")],
    ])
    text = "👥 <b>Шаг 3/6.</b> Кому назначить задачу?"
    if edit:
        await message_or_obj.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message_or_obj.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("tmc:dept:"), TaskCreateState.waiting_dept)
async def tc_got_dept(callback: types.CallbackQuery, state: FSMContext):
    dept_key = callback.data[len("tmc:dept:"):]

    if dept_key == "pick_user":
        # Показываем список всех активных работников
        workers = await get_active_workers()
        if not workers:
            await callback.answer("Нет активных сотрудников", show_alert=True)
            return
        rows = []
        for w in workers:
            pos_label = get_position_display(w)
            rows.append([InlineKeyboardButton(
                text=f"{w.full_name} ({pos_label})",
                callback_data=f"tmc:user:{w.telegram_id}",
            )])
        rows.append([InlineKeyboardButton(text="✖ Отмена", callback_data="tmc:cancel")])
        await state.set_state(TaskCreateState.waiting_user)
        await callback.message.edit_text(
            "👤 <b>Шаг 3/6.</b> Выберите сотрудника:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Назначение на отдел
    await state.update_data(department=dept_key, assigned_to=None, assigned_to_name=None)
    await _ask_priority(callback.message, state, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("tmc:user:"), TaskCreateState.waiting_user)
async def tc_got_user(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data[len("tmc:user:"):])
    worker = await get_user_by_telegram_id(user_id)
    if not worker:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    await state.update_data(
        assigned_to=worker.telegram_id,
        assigned_to_name=worker.full_name,
        department=worker.department,
    )
    await _ask_priority(callback.message, state, edit=True)
    await callback.answer()


async def _ask_priority(msg, state: FSMContext, edit: bool = False):
    await state.set_state(TaskCreateState.waiting_priority)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Срочно",    callback_data="tmc:pri:urgent"),
         InlineKeyboardButton(text="🟡 Нормально", callback_data="tmc:pri:normal"),
         InlineKeyboardButton(text="🟢 Низкий",   callback_data="tmc:pri:low")],
        [InlineKeyboardButton(text="✖ Отмена",     callback_data="tmc:cancel")],
    ])
    text = "⚡ <b>Шаг 4/6.</b> Выберите приоритет:"
    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("tmc:pri:"), TaskCreateState.waiting_priority)
async def tc_got_priority(callback: types.CallbackQuery, state: FSMContext):
    priority = callback.data[len("tmc:pri:"):]
    await state.update_data(priority=priority)
    await _ask_deadline(callback.message, state)
    await callback.answer()


async def _ask_deadline(msg, state: FSMContext):
    await state.set_state(TaskCreateState.waiting_deadline)
    shift_str = _fmt_dl(_deadline_shift_today())
    tmrw_str  = _fmt_dl(_deadline_tomorrow_morning())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🌙 Конец смены {shift_str}", callback_data="tmc:dl:shift")],
        [InlineKeyboardButton(text=f"🌅 Завтра утром {tmrw_str}", callback_data="tmc:dl:tomorrow")],
        [InlineKeyboardButton(text="📅 Без дедлайна",            callback_data="tmc:dl:none")],
        [InlineKeyboardButton(text="✏️ Ввести вручную (ДД.ММ ЧЧ:ММ)", callback_data="tmc:dl:manual")],
        [InlineKeyboardButton(text="✖ Отмена",                   callback_data="tmc:cancel")],
    ])
    await msg.edit_text("📅 <b>Шаг 5/6.</b> Укажите дедлайн:", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("tmc:dl:"), TaskCreateState.waiting_deadline)
async def tc_got_deadline_btn(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data[len("tmc:dl:"):]
    if key == "manual":
        await callback.message.edit_text(
            "✏️ Введите дедлайн в формате <b>ДД.ММ ЧЧ:ММ</b>\n"
            "Пример: <code>25.07 22:00</code>",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    dt = None
    if key == "shift":
        dt = _deadline_shift_today()
    elif key == "tomorrow":
        dt = _deadline_tomorrow_morning()
    # key == "none" → dt остаётся None

    await state.update_data(deadline_dt=dt)
    await _ask_photo(callback.message, state)
    await callback.answer()


@router.message(TaskCreateState.waiting_deadline)
async def tc_got_deadline_text(message: types.Message, state: FSMContext):
    dt = _parse_deadline_text(message.text or "")
    if not dt:
        await message.answer(
            "⚠️ Не могу разобрать дату. Введите в формате <b>ДД.ММ ЧЧ:ММ</b>\n"
            "Пример: <code>25.07 22:00</code>",
            parse_mode="HTML",
        )
        return
    await state.update_data(deadline_dt=dt)
    await _ask_photo(message, state, edit=False)


async def _ask_photo(msg, state: FSMContext, edit: bool = True):
    await state.set_state(TaskCreateState.waiting_photo)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без фото",  callback_data="tmc:skip_photo")],
        [InlineKeyboardButton(text="✖ Отмена",     callback_data="tmc:cancel")],
    ])
    text = "📷 <b>Шаг 6/6.</b> Прикрепи фото (опционально) или пропусти:"
    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "tmc:skip_photo", TaskCreateState.waiting_photo)
async def tc_skip_photo(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(photo_urls=[])
    await _show_task_confirm(callback.message, state, edit=True)
    await callback.answer()


@router.message(TaskCreateState.waiting_photo, F.photo)
async def tc_got_photo(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = list(data.get("photo_urls") or [])
    photos.append(file_id)
    await state.update_data(photo_urls=photos)
    await _show_task_confirm(message, state, edit=False)


@router.message(TaskCreateState.waiting_photo)
async def tc_photo_wrong(message: types.Message, state: FSMContext):
    await message.answer("⚠️ Пришли фото или нажми «Без фото».")


async def _show_task_confirm(msg, state: FSMContext, edit: bool = True):
    data = await state.get_data()
    text = _task_summary_text(data)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать задачу", callback_data="tmc:confirm")],
        [InlineKeyboardButton(text="✖ Отмена",          callback_data="tmc:cancel")],
    ])
    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "tmc:confirm")
async def tc_confirm_create(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    creator = await get_user_by_telegram_id(callback.from_user.id)
    if not creator:
        await callback.answer("Ошибка: пользователь не найден", show_alert=True)
        return

    task_id = await create_task(
        title=data["title"],
        created_by=creator.telegram_id,
        created_by_name=creator.full_name,
        description=data.get("description"),
        assigned_to=data.get("assigned_to"),
        assigned_to_name=data.get("assigned_to_name"),
        department=data.get("department"),
        priority=data.get("priority", "normal"),
        deadline=data.get("deadline_dt"),
        photo_urls=data.get("photo_urls", []),
    )
    await state.clear()

    # Уведомляем исполнителей
    await _notify_task_assigned(bot, task_id, data, creator.full_name)

    dept = data.get("department")
    assignee_str = data.get("assigned_to_name") or _DEPT_LABELS.get(dept, dept or "—")
    short_id = task_id[:8]

    text = (
        f"✅ <b>Задача создана!</b>\n\n"
        f"<b>{data['title']}</b>\n"
        f"👤 Исполнитель: {assignee_str}\n"
        f"⚡ Приоритет: {_PRIORITY_LABELS.get(data.get('priority', 'normal'))}\n"
        f"📅 Дедлайн: {_fmt_dl(data.get('deadline_dt'))}\n"
        f"🔖 ID: <code>{short_id}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Открыть задачу",  callback_data=f"tm:task:{task_id}")],
        [InlineKeyboardButton(text="➕ Ещё задача",       callback_data="tm:new")],
        [InlineKeyboardButton(text="← Управление",       callback_data="tm:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("✅ Создано!")


async def _notify_task_assigned(bot: Bot, task_id: str, data: dict, creator_name: str):
    """Рассылает уведомление исполнителям о новой задаче."""
    dept = data.get("department")
    assigned_to = data.get("assigned_to")
    priority_label = _PRIORITY_LABELS.get(data.get("priority", "normal"))
    dl_str = _fmt_dl(data.get("deadline_dt"))

    text = (
        f"📋 <b>Новая задача от {creator_name}</b>\n\n"
        f"<b>{data['title']}</b>\n"
        f"{data.get('description') or ''}\n\n"
        f"⚡ {priority_label}  |  📅 {dl_str}\n\n"
        f"Откройте раздел <b>Мои задачи</b> для выполнения."
    )
    try:
        if assigned_to:
            await bot.send_message(assigned_to, text, parse_mode="HTML")
        else:
            workers = await get_active_workers(dept if dept != "all" else None)
            for w in workers:
                try:
                    await bot.send_message(w.telegram_id, text, parse_mode="HTML")
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Ошибка уведомления о задаче: {e}")


@router.callback_query(F.data == "tmc:cancel")
async def tc_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "✖ Создание задачи отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Управление задачами", callback_data="tm:main")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── СПИСОК ЗАДАЧ (МЕНЕДЖЕР) ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tm:list:"))
async def tm_task_list(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.role not in _MANAGER_ROLES:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    # tm:list:{status}:{dept}:{page}
    parts = callback.data.split(":")
    status = parts[2] if len(parts) > 2 else "all"
    dept   = parts[3] if len(parts) > 3 else "all"
    page   = int(parts[4]) if len(parts) > 4 else 0

    raw_tasks = await get_tasks(
        status=None if status in ("all", "overdue") else status,
        department=None if dept == "all" else dept,
        limit=500,
    )

    # Фильтр просроченных
    if status == "overdue":
        tasks = [t for t in raw_tasks if _eff_status(t) == "overdue"]
    elif status == "all":
        tasks = raw_tasks
    else:
        tasks = [t for t in raw_tasks if t.status == status]

    total = len(tasks)
    pages = max(1, (total + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE)
    page = max(0, min(page, pages - 1))
    slice_ = tasks[page * TASKS_PER_PAGE : (page + 1) * TASKS_PER_PAGE]

    status_label = {
        "open": "🟠 Открытые", "done": "✅ Выполненные",
        "overdue": "⏰ Просроченные", "cancelled": "🚫 Отменённые",
        "all": "📂 Все",
    }.get(status, status)
    dept_label = _DEPT_LABELS.get(dept, "Все")

    text = (
        f"<b>{status_label}</b> | {dept_label}\n"
        f"Задач: {total}  •  Стр. {page + 1}/{pages}"
    )
    if not slice_:
        text += "\n\n<i>Задач нет</i>"

    rows = []

    # Фильтры по статусу
    status_btns = [
        InlineKeyboardButton(text="🟠", callback_data=f"tm:list:open:{dept}:0"),
        InlineKeyboardButton(text="⏰", callback_data=f"tm:list:overdue:{dept}:0"),
        InlineKeyboardButton(text="✅", callback_data=f"tm:list:done:{dept}:0"),
        InlineKeyboardButton(text="📂", callback_data=f"tm:list:all:{dept}:0"),
    ]
    rows.append(status_btns)

    # Фильтры по отделу
    dept_btns = [
        InlineKeyboardButton(text="🍸", callback_data=f"tm:list:{status}:bar:0"),
        InlineKeyboardButton(text="🍽", callback_data=f"tm:list:{status}:restaurant:0"),
        InlineKeyboardButton(text="🛡", callback_data=f"tm:list:{status}:security:0"),
        InlineKeyboardButton(text="🌐", callback_data=f"tm:list:{status}:all:0"),
    ]
    rows.append(dept_btns)

    # Задачи
    for t in slice_:
        es = _eff_status(t)
        icon = _status_icon(es)
        pri_icon = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}.get(t.priority, "")
        assignee = t.assigned_to_name or _DEPT_LABELS.get(t.department, "—")
        dl = _fmt_dl(t.deadline)
        label = f"{icon}{pri_icon} {t.title[:28]} — {assignee} • {dl}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"tm:task:{t.task_id}")])

    # Пагинация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="←", callback_data=f"tm:list:{status}:{dept}:{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="→", callback_data=f"tm:list:{status}:{dept}:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="← Управление",  callback_data="tm:main")])
    rows.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── ДЕТАЛЬНАЯ КАРТОЧКА ЗАДАЧИ (МЕНЕДЖЕР) ────────────────────────────────────

@router.callback_query(F.data.startswith("tm:task:"))
async def tm_task_detail(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.role not in _MANAGER_ROLES:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    task_id = callback.data[len("tm:task:"):]
    task = await get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    is_assignee = task.assigned_to == user.telegram_id

    es = _eff_status(task)
    icon = _status_icon(es)
    status_label = {"open": "Открыта", "overdue": "Просрочена",
                    "done": "Выполнена", "cancelled": "Отменена"}.get(es, es)
    pri_label = _PRIORITY_LABELS.get(task.priority, task.priority)
    assignee = task.assigned_to_name or _DEPT_LABELS.get(task.department, "—")

    comments_count = len(task.comments or [])
    comments_text = ""
    if task.comments:
        last = task.comments[-1]
        comments_text = (
            f"\n\n💬 <b>Последний комментарий</b> ({last['name']}):\n"
            f"<i>{last['text']}</i>"
        )

    completion_text = ""
    if task.status == "done":
        completion_text = (
            f"\n\n✅ <b>Выполнил:</b> {task.completed_by_name or '—'}\n"
            f"⏰ {_fmt_dt(task.completed_at)}\n"
        )
        if task.completion_comment:
            completion_text += f"💬 {task.completion_comment}\n"

    transfers_text = ""
    if task.transfer_history:
        transfers_text = f"\n\n🔄 Передач: {len(task.transfer_history)}"

    text = (
        f"📋 <b>{task.title}</b>\n"
        f"{icon} {status_label}  |  {pri_label}\n"
        f"{'─' * 30}\n"
    )
    if task.description:
        text += f"\n{task.description}\n"
    text += (
        f"\n👤 <b>Исполнитель:</b> {assignee}\n"
        f"🏢 <b>Отдел:</b> {_DEPT_LABELS.get(task.department, task.department or '—')}\n"
        f"📅 <b>Дедлайн:</b> {_fmt_dl(task.deadline)}\n"
        f"👔 <b>Поставил:</b> {task.created_by_name or '—'}\n"
        f"🕐 <b>Создана:</b> {_fmt_dt(task.created_at)}\n"
    )
    text += completion_text
    if comments_count:
        text += f"\n💬 Комментариев: {comments_count}"
    text += comments_text
    text += transfers_text

    rows = []
    if task.status == "open":
        # Приоритет
        rows.append([
            InlineKeyboardButton(text="🔴 Срочно",    callback_data=f"tme:{task_id}:pri:urgent"),
            InlineKeyboardButton(text="🟡 Нормально", callback_data=f"tme:{task_id}:pri:normal"),
            InlineKeyboardButton(text="🟢 Низкий",   callback_data=f"tme:{task_id}:pri:low"),
        ])
        # Выполнить (для менеджеров/админов/владельцев и исполнителей)
        if user.role in MANAGER_ROLES or is_assignee:
            rows.append([
                InlineKeyboardButton(text="✅ Выполнить", callback_data=f"tme:{task_id}:complete"),
            ])
        # Операции
        rows.append([
            InlineKeyboardButton(text="👤 Переназначить", callback_data=f"tme:{task_id}:reassign"),
            InlineKeyboardButton(text="📅 Дедлайн",       callback_data=f"tme:{task_id}:deadline"),
        ])
        rows.append([
            InlineKeyboardButton(text="💬 Комментарий",  callback_data=f"tme:{task_id}:comment"),
            InlineKeyboardButton(text="🚫 Отменить",     callback_data=f"tme:{task_id}:cancel"),
        ])
    elif task.status == "cancelled":
        rows.append([
            InlineKeyboardButton(text="💬 Комментарий", callback_data=f"tme:{task_id}:comment"),
        ])
    else:
        # done — только комментарий
        rows.append([
            InlineKeyboardButton(text="💬 Комментарий", callback_data=f"tme:{task_id}:comment"),
        ])

    rows.append([InlineKeyboardButton(text="← Список задач", callback_data="tm:list:all:all:0")])
    rows.append([InlineKeyboardButton(text="← Управление",   callback_data="tm:main")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── РЕДАКТИРОВАНИЕ ЗАДАЧИ ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tme:"))
async def tme_dispatch(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user or user.role not in _MANAGER_ROLES:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    # tme:{task_id}:{action}[:{value}]
    parts = callback.data.split(":")
    # parts[0]=tme, parts[1]=task_id (UUID, contains "-"), rebuild properly
    # Format: tme:{uuid}:{action}[:{value}]
    # UUID is 36 chars, so: tme: + 36 + : + action
    raw = callback.data[len("tme:"):]
    task_id = raw[:36]
    rest = raw[37:]  # skip the colon after uuid

    action_parts = rest.split(":", 1)
    action = action_parts[0]
    value  = action_parts[1] if len(action_parts) > 1 else None

    task = await get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    # ── Смена приоритета ──
    if action == "pri" and value:
        await update_task_priority(task_id, value)
        await callback.answer(f"Приоритет: {_PRIORITY_LABELS.get(value, value)}")
        # Перерисовываем карточку
        callback.data = f"tm:task:{task_id}"
        await tm_task_detail(callback)
        return

    # ── Выполнить задачу ──
    if action == "complete":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, выполнить", callback_data=f"tme:{task_id}:do_complete")],
            [InlineKeyboardButton(text="← Назад",           callback_data=f"tm:task:{task_id}")],
        ])
        await callback.message.edit_text(
            f"✅ Отметить задачу <b>{task.title}</b> как выполненную?",
            reply_markup=kb, parse_mode="HTML",
        )
        await callback.answer()
        return

    if action == "do_complete":
        await complete_task_db(
            task_id=task_id,
            by_user_id=user.telegram_id,
            by_user_name=user.full_name,
            comment="",
        )
        await callback.answer("✅ Задача отмечена как выполненная")
        callback.data = f"tm:task:{task_id}"
        await tm_task_detail(callback)
        return

    # ── Отмена задачи ──
    if action == "cancel":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"tme:{task_id}:do_cancel")],
            [InlineKeyboardButton(text="← Назад",         callback_data=f"tm:task:{task_id}")],
        ])
        await callback.message.edit_text(
            f"🚫 Отменить задачу <b>{task.title}</b>?\n\n<i>Это действие нельзя отменить.</i>",
            reply_markup=kb, parse_mode="HTML",
        )
        await callback.answer()
        return

    if action == "do_cancel":
        await cancel_task_db(task_id, user.telegram_id)
        await callback.answer("🚫 Задача отменена")
        callback.data = f"tm:task:{task_id}"
        await tm_task_detail(callback)
        return

    # ── Комментарий ──
    if action == "comment":
        await state.clear()
        await state.set_state(TaskCommentState.waiting_text)
        await state.update_data(task_id=task_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✖ Отмена", callback_data=f"tm:task:{task_id}")],
        ])
        await callback.message.edit_text(
            f"💬 Введите комментарий к задаче <b>{task.title}</b>:",
            reply_markup=kb, parse_mode="HTML",
        )
        await callback.answer()
        return

    # ── Переназначение ──
    if action == "reassign":
        workers = await get_active_workers()
        rows = []
        rows.append([
            InlineKeyboardButton(text="🍸 Весь бар",   callback_data=f"tme:{task_id}:asn_dept:bar"),
            InlineKeyboardButton(text="🍽 Весь зал",   callback_data=f"tme:{task_id}:asn_dept:restaurant"),
            InlineKeyboardButton(text="🛡 Охрана",     callback_data=f"tme:{task_id}:asn_dept:security"),
        ])
        for w in workers:
            dept_lbl = _DEPT_LABELS.get(w.department, "")
            rows.append([InlineKeyboardButton(
                text=f"{w.full_name} ({dept_lbl})",
                callback_data=f"tme:{task_id}:asn:{w.telegram_id}",
            )])
        rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"tm:task:{task_id}")])
        await callback.message.edit_text(
            "👤 Выберите нового исполнителя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    if action == "asn" and value:
        new_uid = int(value)
        worker = await get_user_by_telegram_id(new_uid)
        if not worker:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        old_uid = task.assigned_to
        await reassign_task_db(
            task_id=task_id,
            new_user_id=worker.telegram_id,
            new_user_name=worker.full_name,
            new_department=worker.department,
            by_user_id=user.telegram_id,
            by_user_name=user.full_name,
        )
        # Уведомление старому
        if old_uid and old_uid != worker.telegram_id:
            try:
                await bot.send_message(
                    old_uid,
                    f"🔄 Задача <b>{task.title}</b> была переназначена другому сотруднику.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        # Уведомление новому
        try:
            await bot.send_message(
                worker.telegram_id,
                f"📋 <b>Новая задача</b> от {user.full_name}\n\n"
                f"<b>{task.title}</b>\n{task.description or ''}\n\n"
                f"⚡ {_PRIORITY_LABELS.get(task.priority)}  |  📅 {_fmt_dl(task.deadline)}",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await callback.answer(f"✅ Переназначено: {worker.full_name}")
        callback.data = f"tm:task:{task_id}"
        await tm_task_detail(callback)
        return

    if action == "asn_dept" and value:
        await reassign_task_db(
            task_id=task_id,
            new_user_id=None,
            new_user_name=None,
            new_department=value,
            by_user_id=user.telegram_id,
            by_user_name=user.full_name,
        )
        # Уведомить отдел
        workers = await get_active_workers(value)
        dept_label = _DEPT_LABELS.get(value, value)
        for w in workers:
            try:
                await bot.send_message(
                    w.telegram_id,
                    f"📋 Задача <b>{task.title}</b> назначена на ваш отдел ({dept_label})",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        await callback.answer(f"✅ Назначено на {dept_label}")
        callback.data = f"tm:task:{task_id}"
        await tm_task_detail(callback)
        return

    # ── Изменение дедлайна ──
    if action == "deadline":
        shift_str = _fmt_dl(_deadline_shift_today())
        tmrw_str  = _fmt_dl(_deadline_tomorrow_morning())
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🌙 Конец смены {shift_str}", callback_data=f"tme:{task_id}:dl_set:shift")],
            [InlineKeyboardButton(text=f"🌅 Завтра утром {tmrw_str}", callback_data=f"tme:{task_id}:dl_set:tomorrow")],
            [InlineKeyboardButton(text="📅 Без дедлайна",            callback_data=f"tme:{task_id}:dl_set:none")],
            [InlineKeyboardButton(text="✏️ Ввести вручную",          callback_data=f"tme:{task_id}:dl_set:manual")],
            [InlineKeyboardButton(text="← Назад",                    callback_data=f"tm:task:{task_id}")],
        ])
        await callback.message.edit_text(
            "📅 Выберите новый дедлайн:", reply_markup=kb, parse_mode="HTML",
        )
        await callback.answer()
        return

    if action == "dl_set" and value:
        if value == "manual":
            await state.clear()
            await state.set_state(TaskReassignState.waiting_deadline_text)
            await state.update_data(task_id=task_id)
            await callback.message.edit_text(
                "✏️ Введите дедлайн в формате <b>ДД.ММ ЧЧ:ММ</b>:",
                parse_mode="HTML",
            )
            await callback.answer()
            return
        dt = None
        if value == "shift":
            dt = _deadline_shift_today()
        elif value == "tomorrow":
            dt = _deadline_tomorrow_morning()
        await update_task_deadline(task_id, dt)
        await callback.answer("📅 Дедлайн обновлён")
        callback.data = f"tm:task:{task_id}"
        await tm_task_detail(callback)
        return

    await callback.answer()


# ─── FSM: КОММЕНТАРИЙ К ЗАДАЧЕ ───────────────────────────────────────────────

@router.message(TaskCommentState.waiting_text)
async def tme_got_comment(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    task_id = data.get("task_id")
    user = await get_user_by_telegram_id(message.from_user.id)
    if not task_id or not user:
        await state.clear()
        return
    await add_task_comment_db(task_id, user.telegram_id, user.full_name, message.text.strip())
    await state.clear()

    task = await get_task(task_id)
    await message.answer(
        f"✅ Комментарий добавлен к задаче <b>{task.title if task else task_id}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К задаче", callback_data=f"tm:task:{task_id}")],
        ]),
    )


# ─── FSM: РУЧНОЙ ДЕДЛАЙН (РЕДАКТИРОВАНИЕ) ────────────────────────────────────

@router.message(TaskReassignState.waiting_deadline_text)
async def tme_got_deadline_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("task_id")
    dt = _parse_deadline_text(message.text or "")
    if not dt:
        await message.answer(
            "⚠️ Формат: <b>ДД.ММ ЧЧ:ММ</b>  Пример: <code>25.07 22:00</code>",
            parse_mode="HTML",
        )
        return
    await update_task_deadline(task_id, dt)
    await state.clear()
    await message.answer(
        f"✅ Дедлайн обновлён: {_fmt_dl(dt)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К задаче", callback_data=f"tm:task:{task_id}")],
        ]),
    )


# ─── МОИ ЗАДАЧИ: ДАШБОРД (РАБОТНИК) ─────────────────────────────────────────

@router.callback_query(F.data == "mt:main")
async def mt_dashboard(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    tasks = await get_tasks_for_worker(user.telegram_id, user.department or "")
    open_t    = [t for t in tasks if _eff_status(t) == "open"]
    overdue_t = [t for t in tasks if _eff_status(t) == "overdue"]
    done_t    = [t for t in tasks if t.status == "done"
                 and t.completed_at and t.completed_at.date() == datetime.utcnow().date()]

    text = (
        "📋 <b>Мои задачи</b>\n\n"
        f"🟠 Активных: <b>{len(open_t)}</b>\n"
        f"⏰ Просроченных: <b>{len(overdue_t)}</b>\n"
        f"✅ Выполнено сегодня: <b>{len(done_t)}</b>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟠 Мои задачи",      callback_data="mt:list:open:0"),
         InlineKeyboardButton(text="⏰ Просроченные",     callback_data="mt:list:overdue:0")],
        [InlineKeyboardButton(text="✅ Выполненные",     callback_data="mt:list:done:0"),
         InlineKeyboardButton(text="📂 Все мои",         callback_data="mt:list:all:0")],
        [InlineKeyboardButton(text="📝 Зафиксировать выполненное", callback_data="mt:self_log")],
        [InlineKeyboardButton(text="← Главное меню",     callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ─── СПИСОК ЗАДАЧ (РАБОТНИК) ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mt:list:"))
async def mt_task_list(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    # mt:list:{status}:{page}
    parts = callback.data.split(":")
    status = parts[2] if len(parts) > 2 else "open"
    page   = int(parts[3]) if len(parts) > 3 else 0

    raw = await get_tasks_for_worker(
        user.telegram_id,
        user.department or "",
        status=None if status in ("all", "overdue") else status,
    )
    if status == "overdue":
        tasks = [t for t in raw if _eff_status(t) == "overdue"]
    elif status == "all":
        tasks = raw
    else:
        tasks = [t for t in raw if t.status == status]

    total = len(tasks)
    pages = max(1, (total + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE)
    page  = max(0, min(page, pages - 1))
    slice_ = tasks[page * TASKS_PER_PAGE : (page + 1) * TASKS_PER_PAGE]

    status_label = {
        "open": "🟠 Мои задачи", "done": "✅ Выполненные",
        "overdue": "⏰ Просроченные", "all": "📂 Все мои задачи",
    }.get(status, status)

    text = f"<b>{status_label}</b>\nЗадач: {total}  •  Стр. {page+1}/{pages}"
    if not slice_:
        text += "\n\n<i>Задач нет 👌</i>"

    rows = []
    rows.append([
        InlineKeyboardButton(text="🟠", callback_data="mt:list:open:0"),
        InlineKeyboardButton(text="⏰", callback_data="mt:list:overdue:0"),
        InlineKeyboardButton(text="✅", callback_data="mt:list:done:0"),
        InlineKeyboardButton(text="📂", callback_data="mt:list:all:0"),
    ])

    for t in slice_:
        es = _eff_status(t)
        icon = _status_icon(es)
        pri_icon = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}.get(t.priority, "")
        dl = _fmt_dl(t.deadline)
        by = t.created_by_name or "—"
        label = f"{icon}{pri_icon} {t.title[:30]} • {dl} ({by})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"mt:task:{t.task_id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="←", callback_data=f"mt:list:{status}:{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="→", callback_data=f"mt:list:{status}:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="📝 Зафиксировать",  callback_data="mt:self_log")])
    rows.append([InlineKeyboardButton(text="← Мои задачи",     callback_data="mt:main")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── ДЕТАЛЬНАЯ КАРТОЧКА ЗАДАЧИ (РАБОТНИК) ────────────────────────────────────

@router.callback_query(F.data.startswith("mt:task:"))
async def mt_task_detail(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    task_id = callback.data[len("mt:task:"):]
    task = await get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    es = _eff_status(task)
    icon = _status_icon(es)
    pri_label = _PRIORITY_LABELS.get(task.priority, task.priority)
    status_ru = {"open": "Открыта", "overdue": "Просрочена",
                 "done": "Выполнена", "cancelled": "Отменена"}.get(es, es)

    text = (
        f"📋 <b>{task.title}</b>\n"
        f"{icon} {status_ru}  |  {pri_label}\n"
        f"{'─' * 30}\n"
    )
    if task.description:
        text += f"\n{task.description}\n"
    text += (
        f"\n👔 <b>Поставил:</b> {task.created_by_name or '—'}\n"
        f"📅 <b>Дедлайн:</b> {_fmt_dl(task.deadline)}\n"
        f"🕐 <b>Создана:</b> {_fmt_dt(task.created_at)}\n"
    )
    if task.status == "done":
        text += (
            f"\n✅ <b>Выполнил:</b> {task.completed_by_name or '—'} в {_fmt_dt(task.completed_at)}\n"
        )
        if task.completion_comment:
            text += f"💬 {task.completion_comment}\n"
    if task.comments:
        last = task.comments[-1]
        text += f"\n💬 <b>Комментарий менеджера:</b>\n<i>{last['text']}</i>"

    rows = []
    if task.status == "open":
        rows.append([InlineKeyboardButton(text="✅ Выполнить",   callback_data=f"mt:done:{task_id}")])
    rows.append([InlineKeyboardButton(text="← Мои задачи", callback_data="mt:main")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── FSM: ВЫПОЛНЕНИЕ ЗАДАЧИ (РАБОТНИК) ───────────────────────────────────────

@router.callback_query(F.data.startswith("mt:done:"))
async def mt_start_complete(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data[len("mt:done:"):]
    task = await get_task(task_id)
    if not task or task.status != "open":
        await callback.answer("Задача уже выполнена или не найдена", show_alert=True)
        return
    await state.clear()
    await state.set_state(TaskCompleteState.waiting_comment)
    await state.update_data(task_id=task_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без комментария", callback_data="mtc:skip_comment")],
        [InlineKeyboardButton(text="✖ Отмена",           callback_data=f"mt:task:{task_id}")],
    ])
    await callback.message.edit_text(
        f"✅ Выполняю задачу: <b>{task.title}</b>\n\n"
        f"💬 Добавь комментарий или пропусти:",
        reply_markup=kb, parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "mtc:skip_comment", TaskCompleteState.waiting_comment)
async def mtc_skip_comment(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(comment=None)
    await _ask_completion_photo(callback.message, state, edit=True)
    await callback.answer()


@router.message(TaskCompleteState.waiting_comment)
async def mtc_got_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=message.text.strip() if message.text else None)
    await _ask_completion_photo(message, state, edit=False)


async def _ask_completion_photo(msg, state: FSMContext, edit: bool = True):
    await state.set_state(TaskCompleteState.waiting_photo)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без фото", callback_data="mtc:skip_photo")],
    ])
    text = "📷 Прикрепи фото (например, результат работы) или пропусти:"
    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "mtc:skip_photo", TaskCompleteState.waiting_photo)
async def mtc_skip_photo(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(photos=[])
    await _save_completion(callback.message, state, callback.from_user.id, bot, edit=True)
    await callback.answer()


@router.message(TaskCompleteState.waiting_photo, F.photo)
async def mtc_got_photo(message: types.Message, state: FSMContext, bot: Bot):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = list(data.get("photos") or [])
    photos.append(file_id)
    await state.update_data(photos=photos)
    await _save_completion(message, state, message.from_user.id, bot, edit=False)


@router.message(TaskCompleteState.waiting_photo)
async def mtc_photo_wrong(message: types.Message):
    await message.answer("⚠️ Пришли фото или нажми «Без фото».")


async def _save_completion(msg, state: FSMContext, user_id: int, bot: Bot, edit: bool = True):
    data = await state.get_data()
    task_id = data.get("task_id")
    user = await get_user_by_telegram_id(user_id)
    if not user or not task_id:
        await state.clear()
        return

    ok = await complete_task_db(
        task_id=task_id,
        completed_by=user.telegram_id,
        completed_by_name=user.full_name,
        comment=data.get("comment"),
        photos=data.get("photos", []),
    )
    await state.clear()

    task = await get_task(task_id)
    if ok and task:
        # Уведомляем создателя
        try:
            await bot.send_message(
                task.created_by,
                f"✅ Задача выполнена!\n\n"
                f"<b>{task.title}</b>\n"
                f"👤 Выполнил: {user.full_name}\n"
                f"⏰ {_fmt_dt(datetime.utcnow())}\n"
                + (f"💬 {data.get('comment')}" if data.get("comment") else ""),
                parse_mode="HTML",
            )
        except Exception:
            pass

    text = (
        f"✅ <b>Задача выполнена!</b>\n\n"
        f"<b>{task.title if task else task_id}</b>\n"
        f"⏰ {_fmt_dt(datetime.utcnow())}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Мои задачи", callback_data="mt:main")],
    ])
    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── FSM: САМОФИКСАЦИЯ (РАБОТНИК) ────────────────────────────────────────────

@router.callback_query(F.data == "mt:self_log")
async def mt_start_self_log(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(TaskSelfLogState.waiting_title)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖ Отмена", callback_data="mt:main")],
    ])
    await callback.message.edit_text(
        "📝 <b>Самофиксация выполненного</b>\n\n"
        "Что сделал? Введи <b>название</b>:",
        reply_markup=kb, parse_mode="HTML",
    )
    await callback.answer()


@router.message(TaskSelfLogState.waiting_title)
async def sl_got_title(message: types.Message, state: FSMContext):
    title = message.text.strip() if message.text else ""
    if not title:
        await message.answer("⚠️ Название не может быть пустым:")
        return
    await state.update_data(title=title)
    await state.set_state(TaskSelfLogState.waiting_description)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="sl:skip_desc")],
    ])
    await message.answer(
        f"📋 <b>{title}</b>\n\n📝 Добавь описание (детали) или пропусти:",
        reply_markup=kb, parse_mode="HTML",
    )


@router.callback_query(F.data == "sl:skip_desc", TaskSelfLogState.waiting_description)
async def sl_skip_desc(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(description=None)
    await _sl_ask_photo(callback.message, state, edit=True)
    await callback.answer()


@router.message(TaskSelfLogState.waiting_description)
async def sl_got_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip() if message.text else None)
    await _sl_ask_photo(message, state, edit=False)


async def _sl_ask_photo(msg, state: FSMContext, edit: bool = True):
    await state.set_state(TaskSelfLogState.waiting_photo)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без фото", callback_data="sl:skip_photo")],
    ])
    text = "📷 Прикрепи фото результата или пропусти:"
    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "sl:skip_photo", TaskSelfLogState.waiting_photo)
async def sl_skip_photo(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(photo_urls=[])
    await _sl_save(callback.message, state, callback.from_user.id, edit=True)
    await callback.answer()


@router.message(TaskSelfLogState.waiting_photo, F.photo)
async def sl_got_photo(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = list(data.get("photo_urls") or [])
    photos.append(file_id)
    await state.update_data(photo_urls=photos)
    await _sl_save(message, state, message.from_user.id, edit=False)


@router.message(TaskSelfLogState.waiting_photo)
async def sl_photo_wrong(message: types.Message):
    await message.answer("⚠️ Пришли фото или нажми «Без фото».")


async def _sl_save(msg, state: FSMContext, user_id: int, edit: bool = True):
    data = await state.get_data()
    user = await get_user_by_telegram_id(user_id)
    if not user:
        await state.clear()
        return

    task_id = await create_task(
        title=data["title"],
        created_by=user.telegram_id,
        created_by_name=user.full_name,
        description=data.get("description"),
        assigned_to=user.telegram_id,
        assigned_to_name=user.full_name,
        department=user.department,
        priority="normal",
        photo_urls=data.get("photo_urls", []),
        is_self_logged=True,
    )
    await state.clear()

    text = (
        f"✅ <b>Зафиксировано!</b>\n\n"
        f"<b>{data['title']}</b>\n"
        f"{data.get('description') or ''}\n\n"
        f"⏰ {_fmt_dt(datetime.utcnow())}\n"
        f"🔖 ID: <code>{task_id[:8]}</code>\n\n"
        f"<i>Запись появится в отчётности менеджера.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Мои задачи", callback_data="mt:main")],
    ])
    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── Автопередача при закрытии смены ─────────────────────────────────────────

async def transfer_open_tasks_on_shift_close(user_id: int, bot: Bot) -> int:
    """
    Вызывается при сдаче чек-листа закрытия.
    Передаёт незакрытые задачи другим активным сотрудникам отдела.
    Возвращает количество переданных задач.
    """
    user = await get_user_by_telegram_id(user_id)
    if not user:
        return 0

    open_tasks = await get_tasks_for_worker(user_id, user.department or "", status="open")
    if not open_tasks:
        return 0

    # Ищем коллег в том же отделе (кроме самого пользователя)
    colleagues = [
        w for w in await get_active_workers(user.department)
        if w.telegram_id != user_id
    ]
    if not colleagues:
        return 0

    recipient = colleagues[0]
    transferred = 0

    for task in open_tasks:
        if task.assigned_to != user_id:
            continue
        await reassign_task_db(
            task_id=task.task_id,
            new_user_id=recipient.telegram_id,
            new_user_name=recipient.full_name,
            new_department=recipient.department,
            by_user_id=user_id,
            by_user_name=user.full_name,
        )
        try:
            await bot.send_message(
                user_id,
                f"🔄 Задача <b>{task.title}</b> передана {recipient.full_name} — смена завершена.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        try:
            await bot.send_message(
                recipient.telegram_id,
                f"📋 Вам передана задача от {user.full_name} (прошлая смена)\n\n"
                f"<b>{task.title}</b>\n{task.description or ''}\n"
                f"📅 Дедлайн: {_fmt_dl(task.deadline)}",
                parse_mode="HTML",
            )
        except Exception:
            pass
        transferred += 1

    return transferred
