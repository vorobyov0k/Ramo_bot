# bot/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, BigInteger
from sqlalchemy.sql import func
from bot.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    full_name = Column(String(255))
    role = Column(String(50))
    is_approved = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


class ChecklistExecution(Base):
    __tablename__ = "checklist_executions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    checklist_type = Column(String(50))
    status = Column(String(20), default="in_progress")
    data = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)


class HandoverLog(Base):
    __tablename__ = "handover_logs"

    id = Column(Integer, primary_key=True)
    from_user_id = Column(Integer, nullable=False)
    to_user_id = Column(Integer)
    shift_type = Column(String(50))
    notes = Column(Text)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, server_default=func.now())


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    category = Column(String(50))
    description = Column(Text)
    status = Column(String(20), default="open")
    created_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime)