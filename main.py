# main.py — единая точка входа.
# Тонкая обёртка над bot.main.main(), где подключены ВСЕ роутеры
# (registration, admin, events, promos, task_manager, menu, library,
#  tasks, handover, incident, control), глобальный error-handler,
# миграции БД, инициализация меню/кэша и планировщик акций.
#
# Раньше здесь была устаревшая версия с 7 роутерами и другой БД —
# из-за неё «Управление акциями» и «Режим модерации» не работали
# (их роутеры не были зарегистрированы).
import sys
import asyncio
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_DIR))

from bot.main import main

if __name__ == "__main__":
    asyncio.run(main())
