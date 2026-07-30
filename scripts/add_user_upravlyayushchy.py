"""
Разовое добавление профиля Евгения Шкулепина (управляющий, роль admin)
напрямую в БД, минуя self-регистрацию (у нас уже есть его telegram_id).

Идемпотентно: если пользователь уже есть — обновляет роль/должность,
не создаёт дубликат.

Запуск:
    python scripts/add_user_upravlyayushchy.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from bot.utils.db_connector import (
    get_user_by_telegram_id,
    create_pending_user,
    approve_user,
)

TELEGRAM_ID = 474439785
FULL_NAME = "Евгений Шкулепин"
POSITION = "upravlyayushchy"  # Управляющий (уже в POSITION_MAP → роль admin)
ROLE = "admin"


async def main():
    existing = await get_user_by_telegram_id(TELEGRAM_ID)
    if existing:
        print(f"Пользователь {TELEGRAM_ID} уже существует: "
              f"{existing.full_name}, role={existing.role}, position={existing.position}, "
              f"status={existing.status}, active={existing.active}")
        await approve_user(TELEGRAM_ID, role=ROLE, position=POSITION)
        print(f"→ Обновлено: role={ROLE}, position={POSITION}")
    else:
        await create_pending_user(
            telegram_id=TELEGRAM_ID,
            full_name=FULL_NAME,
            requested_role=ROLE,
            position=POSITION,
        )
        await approve_user(TELEGRAM_ID, role=ROLE, position=POSITION)
        print(f"→ Создан и активирован: {FULL_NAME} (id={TELEGRAM_ID}), "
              f"role={ROLE}, position={POSITION}")

    final = await get_user_by_telegram_id(TELEGRAM_ID)
    print(f"\nИтог: {final.full_name} | role={final.role} | position={final.position} | "
          f"department={final.department} | status={final.status} | active={final.active}")


if __name__ == "__main__":
    asyncio.run(main())
