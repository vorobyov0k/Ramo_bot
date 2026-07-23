# bot/database.py
import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "ramo.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

Base = declarative_base()
engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    """Создаёт таблицы, если их нет."""
    # Импортируем модели, чтобы SQLAlchemy их зарегистрировала
    from bot.models import User, ChecklistExecution, HandoverLog, Incident  # noqa: F401

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ База данных инициализирована")


async def get_session() -> AsyncSession:
    async with async_session() as session:
        return session