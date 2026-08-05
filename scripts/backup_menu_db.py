#!/usr/bin/env python3
"""Backup menu.db before/after photo upload to prevent data loss."""
import shutil
from pathlib import Path
from time import time

DATA_DIR = Path(__file__).parent.parent / "data"
MENU_DB = DATA_DIR / "menu.db"
BACKUP_FILE = DATA_DIR / f"menu.db.bak-{int(time())}"

if not MENU_DB.exists():
    print(f"❌ Файл {MENU_DB} не найден")
    exit(1)

try:
    shutil.copy2(MENU_DB, BACKUP_FILE)
    size_kb = BACKUP_FILE.stat().st_size / 1024
    print(f"✅ Бэкап создан: {BACKUP_FILE.name} ({size_kb:.1f} KB)")
except Exception as e:
    print(f"❌ Ошибка при создании бэкапа: {e}")
    exit(1)
