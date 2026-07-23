# bot/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Required configs
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0")) if os.getenv("ADMIN_TELEGRAM_ID") else None
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

# Google Sheets integration
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
GOOGLE_CLIENT_SECRET_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")

# Storage and cache
# Пути к БД якорим на корень проекта (родитель папки bot/), а НЕ на текущую
# рабочую директорию — иначе при запуске из другого CWD (PyCharm, планировщик)
# sqlite открывал бы пустые файлы data/*.db и получал «no such table».
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _anchored(env_name: str, default: str) -> Path:
    p = Path(os.getenv(env_name, default))
    return p if p.is_absolute() else _PROJECT_ROOT / p


CACHE_DIR = _anchored("CACHE_DIR", "data/cache")
DATA_DIR = _anchored("DATA_DIR", "data")
CACHE_SYNC_INTERVAL_MINUTES = int(os.getenv("CACHE_SYNC_INTERVAL_MINUTES", "60"))
ROUTINE_INTERVAL_DAYS = int(os.getenv("ROUTINE_INTERVAL_DAYS", "7"))

# Bot settings
BOT_LANGUAGE = os.getenv("BOT_LANGUAGE", "ru")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

# Optional AI Database integration
AI_DB_API_URL = os.getenv("AI_DB_API_URL")
AI_DB_API_KEY = os.getenv("AI_DB_API_KEY")

# Validation
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверьте файл .env")

if ":" not in BOT_TOKEN:
    raise ValueError(f"BOT_TOKEN невалидный: {BOT_TOKEN[:10]}... Должен содержать ':'")