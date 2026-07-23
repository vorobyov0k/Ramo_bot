"""
Коннектор к SQLite БД.
Хранит: пользователей, выполнение чек-листов, handover, инциденты, прогресс.
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey, text
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from bot import config

Base = declarative_base()

# ─── Модели ───

class User(Base):
    __tablename__ = "bot_users"

    telegram_id = Column(Integer, primary_key=True)
    full_name = Column(String(255))
    role = Column(String(50))  # admin, manager, barman, waiter, security, newcomer
    requested_role = Column(String(50), nullable=True)
    department = Column(String(50))
    phone = Column(String(50), nullable=True)
    hire_date = Column(DateTime, nullable=True)
    mentor_id = Column(Integer, ForeignKey("bot_users.telegram_id"), nullable=True)
    active = Column(Boolean, default=False)
    status = Column(String(20), default="pending")  # pending / active / rejected
    timezone = Column(String(50), default="Europe/Moscow")
    position = Column(String(100), nullable=True)   # slug должности (barman, chef, bar_manager, ...)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChecklistExecution(Base):
    __tablename__ = "checklist_executions"

    execution_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    checklist_type = Column(String(50))  # opening, closing, duty_period_1, etc.
    user_id = Column(Integer, ForeignKey("bot_users.telegram_id"))
    shift_id = Column(String(100), nullable=True)
    items = Column(JSON, default=list)  # [{item_id, completed, timestamp, notes, photo_url}]
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="in_progress")  # in_progress, submitted, verified, disputed
    verified_by = Column(Integer, ForeignKey("bot_users.telegram_id"), nullable=True)
    dispute_reason = Column(Text, nullable=True)
    dispute_resolution = Column(Text, nullable=True)
    archived = Column(Boolean, default=False)


class HandoverLog(Base):
    __tablename__ = "handover_logs"

    handover_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_user_id = Column(Integer, ForeignKey("bot_users.telegram_id"))
    from_shift_id = Column(String(100), nullable=True)
    from_department = Column(String(50))
    to_shift_id = Column(String(100), nullable=True)
    to_department = Column(String(50), nullable=True)
    message = Column(Text)
    importance = Column(String(20), default="normal")  # urgent, normal
    photo_urls = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    read_by = Column(JSON, default=list)  # [{user_id, timestamp}]
    tags = Column(JSON, default=list)
    visible_to = Column(JSON, default=list)
    accepted_by = Column(Integer, ForeignKey("bot_users.telegram_id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)


class IncidentReport(Base):
    __tablename__ = "incidents_reports"

    incident_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_type = Column(String(50))  # spill, conflict, injury, accident, damage, lost_item
    reported_by = Column(Integer, ForeignKey("bot_users.telegram_id"))
    datetime_occurred = Column(DateTime)
    location = Column(String(255), nullable=True)
    description = Column(Text)
    witnesses = Column(JSON, default=list)  # [{user_id, name}]
    photo_urls = Column(JSON, default=list)
    status = Column(String(20), default="happened")  # happened, needs_action, resolved, closed
    assigned_to = Column(Integer, ForeignKey("bot_users.telegram_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)


class Event(Base):
    __tablename__ = "events"

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(20))  # booking, announcement, holiday, birthday
    title = Column(String(255))
    description = Column(Text, nullable=True)
    event_date = Column(DateTime)
    meta = Column(JSON, default=dict)  # phone, guest_count, etc.
    created_by = Column(Integer, ForeignKey("bot_users.telegram_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class OnboardingProgress(Base):
    __tablename__ = "onboarding_progress"

    progress_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    newcomer_id = Column(Integer, ForeignKey("bot_users.telegram_id"))
    stage = Column(String(20))  # day1, week1, month1
    checklist_items = Column(JSON, default=list)
    quiz_results = Column(JSON, default=list)
    mentor_id = Column(Integer, ForeignKey("bot_users.telegram_id"), nullable=True)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class PromoConfig(Base):
    __tablename__ = "promo_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    promo_key = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    title = Column(String(200))
    description = Column(Text)
    weekday = Column(Integer, nullable=True)  # 0=Пн … 6=Вс, None=ежедневно
    time_start = Column(String(10), nullable=True)
    time_end = Column(String(10), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, nullable=True)


class PromoLog(Base):
    __tablename__ = "promo_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    message_text = Column(Text)
    recipients_count = Column(Integer, default=0)


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255))
    description = Column(Text, nullable=True)
    priority = Column(String(20), default="normal")   # urgent / normal / low
    status = Column(String(20), default="open")        # open / done / cancelled

    created_by = Column(Integer, ForeignKey("bot_users.telegram_id"))
    created_by_name = Column(String(255), nullable=True)

    assigned_to = Column(Integer, ForeignKey("bot_users.telegram_id"), nullable=True)
    assigned_to_name = Column(String(255), nullable=True)
    department = Column(String(50), nullable=True)    # bar / restaurant / security / all

    deadline = Column(DateTime, nullable=True)

    photo_urls = Column(JSON, default=list)            # file_ids от создателя

    completed_by = Column(Integer, ForeignKey("bot_users.telegram_id"), nullable=True)
    completed_by_name = Column(String(255), nullable=True)
    completed_at = Column(DateTime, nullable=True)
    completion_comment = Column(Text, nullable=True)
    completion_photos = Column(JSON, default=list)

    is_self_logged = Column(Boolean, default=False)

    cancelled_by = Column(Integer, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    comments = Column(JSON, default=list)
    # [{user_id, name, text, ts}]
    transfer_history = Column(JSON, default=list)
    # [{from_id, from_name, to_id, to_name, ts}]


class ShiftLog(Base):
    __tablename__ = "shift_logs"

    shift_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("bot_users.telegram_id"))
    user_name = Column(String(255))
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    close_comment = Column(Text, nullable=True)


_PROMO_DEFAULTS: List[Dict[str, Any]] = [
    {
        "promo_key": "weekday_0", "weekday": 0, "is_active": True,
        "title": "\U0001f379 День коктейля",
        "description": "1+1 на все коктейли (покупаешь 1 — второй в подарок)",
    },
    {
        "promo_key": "weekday_1", "weekday": 1, "is_active": True,
        "title": "\U0001f943 День настоек",
        "description": "1+1 на все настойки (покупаешь 1 — вторую в подарок)",
    },
    {
        "promo_key": "weekday_2", "weekday": 2, "is_active": True,
        "title": "\U0001f377 Винный день",
        "description": "1+1 на все вина (покупаешь 1 — второе в подарок)",
    },
    {
        "promo_key": "weekday_3", "weekday": 3, "is_active": True,
        "title": "\U0001f37a Пивной день",
        "description": "1+1 на все сорта пива (покупаешь 1 — второе в подарок)",
    },
    {
        "promo_key": "lunch_15", "weekday": None, "is_active": True,
        "title": "\U0001f37d Обеденная акция",
        "description": "−15% на всё меню с 12:00 до 17:00",
        "time_start": "12:00", "time_end": "17:00",
    },
    {
        "promo_key": "promo_flyer", "weekday": None, "is_active": False,
        "title": "\U0001f3ab Промо-листовка (гаджет-бар)",
        "description": (
            "чек в гаджет-баре от 1000₽ = напиток в подарок\n"
            "  • Лимонад классический\n"
            "  • Американо 0,3\n"
            "  • Капучино 0,2\n"
            "  • Латте 0,2\n"
            "Выдаётся ТОЛЬКО после оплаты. 1 подарок на 1 чек."
        ),
    },
]


# ─── Engine & Session ───

DATABASE_URL = f"sqlite+aiosqlite:///{config.DATA_DIR}/db.sqlite"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Создаёт таблицы при первом запуске и применяет миграции."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Миграция: добавляем новые колонки если их ещё нет.
        # ALTER для уже существующей колонки бросает исключение — глотаем.
        for col_sql in [
            # bot_users — колонки, добавленные после первого релиза
            "ALTER TABLE bot_users ADD COLUMN position VARCHAR(100)",
            "ALTER TABLE bot_users ADD COLUMN requested_role VARCHAR(50)",
            "ALTER TABLE bot_users ADD COLUMN timezone VARCHAR(50) DEFAULT 'Europe/Moscow'",
            "ALTER TABLE bot_users ADD COLUMN mentor_id INTEGER REFERENCES bot_users(telegram_id)",
            "ALTER TABLE bot_users ADD COLUMN hire_date DATETIME",
            # handover_logs — приём смены
            "ALTER TABLE handover_logs ADD COLUMN accepted_by INTEGER REFERENCES bot_users(telegram_id)",
            "ALTER TABLE handover_logs ADD COLUMN accepted_at DATETIME",
            "ALTER TABLE checklist_executions ADD COLUMN archived BOOLEAN DEFAULT 0",
        ]:
            try:
                await conn.execute(text(col_sql))
            except Exception:
                pass  # колонка уже существует — игнорируем
        # Миграция: security → technician
        await conn.execute(text(
            "UPDATE bot_users SET role='user', position='technician' "
            "WHERE role='security' AND (position IS NULL OR position='security')"
        ))


# ─── CRUD методы ───

async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    async with async_session() as session:
        return await session.get(User, telegram_id)


async def create_pending_user(
    telegram_id: int,
    full_name: str,
    requested_role: str,
    department: Optional[str] = None,
    position: Optional[str] = None,
) -> User:
    async with async_session() as session:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            requested_role=requested_role,
            department=department,
            position=position,
            status="pending",
            active=False,
        )
        session.add(user)
        await session.commit()
        return user


async def approve_user(
    telegram_id: int,
    role: Optional[str] = None,
    position: Optional[str] = None,
) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.status = "active"
            user.active = True
            user.role = role or user.requested_role
            if position:
                user.position = position
            await session.commit()


async def reject_user(telegram_id: int) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.status = "rejected"
            user.active = False
            await session.commit()


async def save_checklist_execution(
    checklist_type: str,
    user_id: int,
    shift_id: Optional[str] = None,
    items: Optional[List[Dict]] = None,
) -> str:
    execution_id = str(uuid.uuid4())
    async with async_session() as session:
        execution = ChecklistExecution(
            execution_id=execution_id,
            checklist_type=checklist_type,
            user_id=user_id,
            shift_id=shift_id,
            items=items or [],
        )
        session.add(execution)
        await session.commit()
    return execution_id


async def save_handover_log(
    from_user_id: int,
    message: str,
    from_department: str,
    importance: str = "normal",
    photo_urls: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    visible_to: Optional[List[int]] = None,
) -> str:
    handover_id = str(uuid.uuid4())
    async with async_session() as session:
        log = HandoverLog(
            handover_id=handover_id,
            from_user_id=from_user_id,
            from_department=from_department,
            message=message,
            importance=importance,
            photo_urls=photo_urls or [],
            tags=tags or [],
            visible_to=visible_to or [],
        )
        session.add(log)
        await session.commit()
    return handover_id


async def save_incident_report(
    incident_type: str,
    reported_by: int,
    description: str,
    datetime_occurred: datetime,
    location: Optional[str] = None,
    witnesses: Optional[List[Dict]] = None,
    photo_urls: Optional[List[str]] = None,
    status: str = "happened",
) -> str:
    incident_id = str(uuid.uuid4())
    async with async_session() as session:
        incident = IncidentReport(
            incident_id=incident_id,
            incident_type=incident_type,
            reported_by=reported_by,
            description=description,
            datetime_occurred=datetime_occurred,
            location=location,
            witnesses=witnesses or [],
            photo_urls=photo_urls or [],
            status=status,
        )
        session.add(incident)
        await session.commit()
    return incident_id


async def get_user_access_level(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает роль и отдел пользователя для проверки прав."""
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        return None
    return {
        "telegram_id": user.telegram_id,
        "role": user.role,
        "department": user.department,
        "status": user.status,
        "active": user.active,
    }


# ─── Event CRUD ───

async def create_event(
    event_type: str,
    title: str,
    event_date: datetime,
    description: Optional[str] = None,
    meta: Optional[Dict] = None,
    created_by: Optional[int] = None,
) -> str:
    event_id = str(uuid.uuid4())
    async with async_session() as session:
        event = Event(
            event_id=event_id,
            event_type=event_type,
            title=title,
            event_date=event_date,
            description=description,
            meta=meta or {},
            created_by=created_by,
        )
        session.add(event)
        await session.commit()
    return event_id


async def get_events_by_type(event_type: str, limit: int = 20) -> List["Event"]:
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(Event)
            .where(Event.event_type == event_type, Event.is_active == True)
            .order_by(Event.event_date)
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_upcoming_events(event_type: Optional[str] = None, days: int = 30) -> List["Event"]:
    from sqlalchemy import select
    from datetime import timedelta
    now = datetime.utcnow()
    until = now + timedelta(days=days)
    async with async_session() as session:
        query = (
            select(Event)
            .where(Event.is_active == True, Event.event_date >= now, Event.event_date <= until)
        )
        if event_type:
            query = query.where(Event.event_type == event_type)
        result = await session.execute(query.order_by(Event.event_date))
        return list(result.scalars().all())


async def delete_event(event_id: str) -> bool:
    async with async_session() as session:
        event = await session.get(Event, event_id)
        if not event:
            return False
        event.is_active = False
        await session.commit()
        return True


# ─── Admin CRUD ───

async def get_all_users(status: Optional[str] = None) -> List[User]:
    from sqlalchemy import select
    async with async_session() as session:
        query = select(User)
        if status:
            query = query.where(User.status == status)
        result = await session.execute(query.order_by(User.created_at.desc()))
        return list(result.scalars().all())


async def update_user_role(telegram_id: int, new_role: str) -> bool:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if not user:
            return False
        user.role = new_role
        await session.commit()
        return True


async def update_user_position(telegram_id: int, new_position: str) -> bool:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if not user:
            return False
        user.position = new_position
        await session.commit()
        return True


async def deactivate_user(telegram_id: int) -> bool:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if not user:
            return False
        user.status = "rejected"
        user.active = False
        await session.commit()
        return True


async def delete_user(telegram_id: int) -> bool:
    """Удаление пользователя из БД (физическое удаление)."""
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if not user:
            return False
        await session.delete(user)
        await session.commit()
        return True


async def get_checklist_execution(execution_id: str) -> Optional[ChecklistExecution]:
    """Одно выполнение чек-листа по его id (для детального отчёта)."""
    async with async_session() as session:
        return await session.get(ChecklistExecution, execution_id)


async def get_recent_checklists(limit: int = 20) -> List[ChecklistExecution]:
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(ChecklistExecution)
            .where(ChecklistExecution.archived == False)
            .order_by(ChecklistExecution.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def archive_checklist(execution_id: str) -> bool:
    async with async_session() as session:
        ex = await session.get(ChecklistExecution, execution_id)
        if not ex:
            return False
        ex.archived = True
        await session.commit()
        return True


async def archive_all_checklists() -> int:
    """Архивирует все неархивированные чек-листы. Возвращает кол-во записей."""
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(ChecklistExecution).where(ChecklistExecution.archived == False)
        )
        rows = list(result.scalars().all())
        for ex in rows:
            ex.archived = True
        await session.commit()
        return len(rows)


async def get_archived_checklists(limit: int = 50) -> List[ChecklistExecution]:
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(ChecklistExecution)
            .where(ChecklistExecution.archived == True)
            .order_by(ChecklistExecution.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_recent_incidents(limit: int = 20) -> List[IncidentReport]:
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(IncidentReport)
            .order_by(IncidentReport.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_recent_handovers(limit: int = 20) -> List[HandoverLog]:
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(HandoverLog)
            .order_by(HandoverLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_last_handover() -> Optional["HandoverLog"]:
    """Возвращает самую свежую запись передачи смены."""
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(HandoverLog).order_by(HandoverLog.created_at.desc()).limit(1)
        )
        return result.scalars().first()


async def accept_handover(handover_id: str, accepted_by_id: int) -> bool:
    """Отмечает передачу как принятую. Возвращает True если обновление прошло."""
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(HandoverLog).where(HandoverLog.handover_id == handover_id)
        )
        log = result.scalars().first()
        if not log:
            return False
        log.accepted_by = accepted_by_id
        log.accepted_at = datetime.utcnow()
        await session.commit()
        return True


# ─── Promo CRUD ───

async def init_promos() -> None:
    """Засевает promo_configs дефолтными акциями при первом запуске."""
    from sqlalchemy import select
    async with async_session() as session:
        for defaults in _PROMO_DEFAULTS:
            key = defaults["promo_key"]
            exists = (await session.execute(
                select(PromoConfig).where(PromoConfig.promo_key == key)
            )).scalar_one_or_none()
            if not exists:
                obj = PromoConfig(**{k: v for k, v in defaults.items()
                                     if k in PromoConfig.__table__.columns.keys()})
                session.add(obj)
        await session.commit()


async def get_all_promos() -> List[PromoConfig]:
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(PromoConfig).order_by(PromoConfig.id)
        )
        return list(result.scalars().all())


async def get_promos_for_day(weekday: int) -> List[PromoConfig]:
    """Активные акции для указанного дня недели (0=Пн … 6=Вс)."""
    from sqlalchemy import select, or_
    async with async_session() as session:
        result = await session.execute(
            select(PromoConfig)
            .where(
                PromoConfig.is_active == True,
                or_(PromoConfig.weekday == weekday, PromoConfig.weekday == None),
            )
            .order_by(PromoConfig.id)
        )
        return list(result.scalars().all())


async def toggle_promo(promo_key: str) -> Optional[bool]:
    """Переключает is_active. Возвращает новое значение или None если не найдено."""
    from sqlalchemy import select
    async with async_session() as session:
        promo = (await session.execute(
            select(PromoConfig).where(PromoConfig.promo_key == promo_key)
        )).scalar_one_or_none()
        if not promo:
            return None
        promo.is_active = not promo.is_active
        await session.commit()
        return promo.is_active


async def update_promo_description(
    promo_key: str, description: str, updated_by: Optional[int] = None
) -> bool:
    from sqlalchemy import select
    async with async_session() as session:
        promo = (await session.execute(
            select(PromoConfig).where(PromoConfig.promo_key == promo_key)
        )).scalar_one_or_none()
        if not promo:
            return False
        promo.description = description
        promo.updated_by = updated_by
        promo.updated_at = datetime.utcnow()
        await session.commit()
        return True


async def log_promo_broadcast(message_text: str, recipients_count: int) -> None:
    async with async_session() as session:
        log = PromoLog(message_text=message_text, recipients_count=recipients_count)
        session.add(log)
        await session.commit()


async def get_promo_logs(limit: int = 10) -> List[PromoLog]:
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(PromoLog).order_by(PromoLog.sent_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


# ─── Task CRUD ───

async def create_task(
    title: str,
    created_by: int,
    created_by_name: str,
    description: Optional[str] = None,
    assigned_to: Optional[int] = None,
    assigned_to_name: Optional[str] = None,
    department: Optional[str] = None,
    priority: str = "normal",
    deadline: Optional[datetime] = None,
    photo_urls: Optional[List[str]] = None,
    is_self_logged: bool = False,
) -> str:
    task_id = str(uuid.uuid4())
    async with async_session() as session:
        task = Task(
            task_id=task_id,
            title=title,
            description=description,
            priority=priority,
            status="open" if not is_self_logged else "done",
            created_by=created_by,
            created_by_name=created_by_name,
            assigned_to=assigned_to,
            assigned_to_name=assigned_to_name,
            department=department,
            deadline=deadline,
            photo_urls=photo_urls or [],
            is_self_logged=is_self_logged,
            completed_by=created_by if is_self_logged else None,
            completed_by_name=created_by_name if is_self_logged else None,
            completed_at=datetime.utcnow() if is_self_logged else None,
        )
        session.add(task)
        await session.commit()
    return task_id


async def get_task(task_id: str) -> Optional[Task]:
    async with async_session() as session:
        return await session.get(Task, task_id)


async def get_tasks(
    status: Optional[str] = None,
    department: Optional[str] = None,
    assigned_to: Optional[int] = None,
    created_by: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Task]:
    from sqlalchemy import select
    async with async_session() as session:
        query = select(Task)
        if status and status != "overdue":
            query = query.where(Task.status == status)
        if department and department != "all":
            query = query.where(Task.department == department)
        if assigned_to is not None:
            query = query.where(Task.assigned_to == assigned_to)
        if created_by is not None:
            query = query.where(Task.created_by == created_by)
        query = query.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())


async def get_tasks_for_worker(
    user_id: int,
    department: str,
    status: Optional[str] = None,
) -> List[Task]:
    """Задачи для работника: назначены лично ИЛИ на его отдел."""
    from sqlalchemy import select, or_, and_
    async with async_session() as session:
        query = select(Task).where(
            or_(
                Task.assigned_to == user_id,
                and_(Task.assigned_to == None, Task.department == department),
                and_(Task.assigned_to == None, Task.department == "all"),
            )
        )
        if status and status != "overdue":
            query = query.where(Task.status == status)
        query = query.order_by(Task.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def complete_task_db(
    task_id: str,
    completed_by: int,
    completed_by_name: str,
    comment: Optional[str] = None,
    photos: Optional[List[str]] = None,
) -> bool:
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task or task.status != "open":
            return False
        task.status = "done"
        task.completed_by = completed_by
        task.completed_by_name = completed_by_name
        task.completed_at = datetime.utcnow()
        task.completion_comment = comment
        task.completion_photos = photos or []
        task.updated_at = datetime.utcnow()
        await session.commit()
        return True


async def reassign_task_db(
    task_id: str,
    new_user_id: Optional[int],
    new_user_name: Optional[str],
    new_department: Optional[str],
    by_user_id: int,
    by_user_name: str,
) -> bool:
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return False
        old_entry = {
            "from_id": task.assigned_to,
            "from_name": task.assigned_to_name or "—",
            "to_id": new_user_id,
            "to_name": new_user_name or new_department or "—",
            "ts": datetime.utcnow().isoformat(),
            "by": by_user_name,
        }
        history = list(task.transfer_history or [])
        history.append(old_entry)
        task.transfer_history = history
        task.assigned_to = new_user_id
        task.assigned_to_name = new_user_name
        if new_department:
            task.department = new_department
        task.updated_at = datetime.utcnow()
        await session.commit()
        return True


async def cancel_task_db(task_id: str, cancelled_by: int) -> bool:
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task or task.status not in ("open",):
            return False
        task.status = "cancelled"
        task.cancelled_by = cancelled_by
        task.cancelled_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        await session.commit()
        return True


async def add_task_comment_db(
    task_id: str, user_id: int, user_name: str, text: str
) -> bool:
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return False
        comments = list(task.comments or [])
        comments.append({
            "user_id": user_id,
            "name": user_name,
            "text": text,
            "ts": datetime.utcnow().isoformat(),
        })
        task.comments = comments
        task.updated_at = datetime.utcnow()
        await session.commit()
        return True


async def update_task_priority(task_id: str, priority: str) -> bool:
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return False
        task.priority = priority
        task.updated_at = datetime.utcnow()
        await session.commit()
        return True


async def update_task_deadline(task_id: str, deadline: Optional[datetime]) -> bool:
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return False
        task.deadline = deadline
        task.updated_at = datetime.utcnow()
        await session.commit()
        return True


# ─── Смены ───

async def get_active_shift(user_id: int) -> Optional[ShiftLog]:
    """Открытая смена пользователя (ещё не закрыта)."""
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(ShiftLog)
            .where(ShiftLog.user_id == user_id, ShiftLog.ended_at == None)
            .order_by(ShiftLog.started_at.desc())
            .limit(1)
        )
        return result.scalars().first()


async def open_shift(user_id: int, user_name: str) -> str:
    """Открыть смену. Возвращает shift_id."""
    shift_id = str(uuid.uuid4())
    async with async_session() as session:
        shift = ShiftLog(shift_id=shift_id, user_id=user_id, user_name=user_name)
        session.add(shift)
        await session.commit()
    return shift_id


async def close_shift(shift_id: str, comment: Optional[str] = None) -> bool:
    """Закрыть смену."""
    async with async_session() as session:
        shift = await session.get(ShiftLog, shift_id)
        if not shift or shift.ended_at is not None:
            return False
        shift.ended_at = datetime.utcnow()
        shift.close_comment = comment
        await session.commit()
        return True


# ─── Счётчики для home screen ───

async def get_today_events_count() -> int:
    """Кол-во событий (броней, анонсов, праздников) на сегодня (UTC+3 Москва)."""
    from sqlalchemy import select, func
    from datetime import timezone, timedelta
    msk = timezone(timedelta(hours=3))
    now_msk = datetime.now(msk)
    today_start = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    today_start_utc = today_start.astimezone(timezone.utc).replace(tzinfo=None)
    today_end_utc = today_end.astimezone(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).select_from(Event).where(
                Event.is_active == True,
                Event.event_date >= today_start_utc,
                Event.event_date < today_end_utc,
            )
        )
        return result.scalar() or 0


async def get_today_open_tasks_count(user_id: int, department: Optional[str]) -> int:
    """Кол-во открытых задач на пользователя (лично или по отделу)."""
    from sqlalchemy import select, func, or_, and_
    async with async_session() as session:
        conds = [
            Task.assigned_to == user_id,
            and_(Task.assigned_to == None, Task.department == "all"),
        ]
        if department:
            conds.append(and_(Task.assigned_to == None, Task.department == department))
        result = await session.execute(
            select(func.count()).select_from(Task).where(
                Task.status == "open",
                or_(*conds),
            )
        )
        return result.scalar() or 0


async def get_active_workers(department: Optional[str] = None) -> List[User]:
    """Активные работники, опционально по отделу. Исключает admin/pm."""
    from sqlalchemy import select
    async with async_session() as session:
        query = select(User).where(
            User.status == "active",
            User.role.notin_(["admin", "pm"]),
        )
        if department and department != "all":
            query = query.where(User.department == department)
        result = await session.execute(query.order_by(User.full_name))
        return list(result.scalars().all())
