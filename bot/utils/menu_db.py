"""
Утилиты для работы с меню из data/menu.db (отдельная БД, не SQLAlchemy).
"""
import sqlite3
from pathlib import Path
from typing import Optional, List

from bot import config

_MENU_DB = str(config.DATA_DIR / "menu.db")


def init_menu_db() -> None:
    """Применяет миграции для photo_id в dishes и drinks."""
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    for sql in [
        "ALTER TABLE dishes ADD COLUMN photo_id TEXT",
        "ALTER TABLE drinks ADD COLUMN photo_id TEXT",
        "ALTER TABLE categories ADD COLUMN group_name TEXT",
    ]:
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass  # колонка уже существует
    conn.commit()
    conn.close()


def get_categories(type_: str) -> List[dict]:
    """Список категорий для кухни или бара: [{"id", "name", "group_name"}, ...].

    group_name — если заполнено, категория входит в общую подгруппу
    (например, стили вина внутри «Вина») и не должна показываться
    как отдельный пункт верхнего уровня в клиентском меню.
    """
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute(
        "SELECT id, name, group_name FROM categories WHERE type=? ORDER BY sort_order, name",
        (type_,),
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "group_name": r[2]} for r in rows]


def get_dishes_by_category(category_name: str) -> List[dict]:
    """Блюда кухни в категории по её названию."""
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute(
        """
        SELECT d.id, d.name, d.price,
               d.is_spicy, d.is_vegetarian, d.is_new, d.is_healthy,
               d.description, d.photo_id
        FROM dishes d
        JOIN categories cat ON d.category_id = cat.id
        WHERE cat.name = ? AND cat.type = 'kitchen'
        ORDER BY d.name
        """,
        (category_name,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0], "name": r[1], "price": r[2],
            "is_spicy": r[3], "is_vegetarian": r[4],
            "is_new": r[5], "is_healthy": r[6],
            "description": r[7], "photo_id": r[8],
        }
        for r in rows
    ]


def get_dish_by_id(dish_id: int) -> Optional[dict]:
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute(
        """
        SELECT d.id, d.name, d.price,
               d.is_spicy, d.is_vegetarian, d.is_new, d.is_healthy,
               d.description, d.photo_id, cat.name
        FROM dishes d
        JOIN categories cat ON d.category_id = cat.id
        WHERE d.id = ?
        """,
        (dish_id,),
    )
    r = c.fetchone()
    conn.close()
    if not r:
        return None
    return {
        "id": r[0], "name": r[1], "price": r[2],
        "is_spicy": r[3], "is_vegetarian": r[4],
        "is_new": r[5], "is_healthy": r[6],
        "description": r[7], "photo_id": r[8],
        "category_name": r[9],
    }


def get_drinks_by_category(category_name: str) -> List[dict]:
    """Напитки бара в категории по её названию."""
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute(
        """
        SELECT d.id, d.name, d.price,
               d.is_non_alcoholic, d.is_vegetarian, d.is_new, d.is_healthy,
               d.description, d.photo_id
        FROM drinks d
        JOIN categories cat ON d.category_id = cat.id
        WHERE cat.name = ? AND cat.type = 'bar'
        ORDER BY d.name
        """,
        (category_name,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0], "name": r[1], "price": r[2],
            "is_non_alcoholic": r[3], "is_vegetarian": r[4],
            "is_new": r[5], "is_healthy": r[6],
            "description": r[7], "photo_id": r[8],
        }
        for r in rows
    ]


def get_drink_by_id(drink_id: int) -> Optional[dict]:
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute(
        """
        SELECT d.id, d.name, d.price,
               d.is_non_alcoholic, d.is_vegetarian, d.is_new, d.is_healthy,
               d.description, d.photo_id, cat.name
        FROM drinks d
        JOIN categories cat ON d.category_id = cat.id
        WHERE d.id = ?
        """,
        (drink_id,),
    )
    r = c.fetchone()
    conn.close()
    if not r:
        return None
    return {
        "id": r[0], "name": r[1], "price": r[2],
        "is_non_alcoholic": r[3], "is_vegetarian": r[4],
        "is_new": r[5], "is_healthy": r[6],
        "description": r[7], "photo_id": r[8],
        "category_name": r[9],
    }


def update_dish_photo(dish_id: int, photo_id: str) -> bool:
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute("UPDATE dishes SET photo_id = ? WHERE id = ?", (photo_id, dish_id))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def update_drink_photo(drink_id: int, photo_id: str) -> bool:
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute("UPDATE drinks SET photo_id = ? WHERE id = ?", (photo_id, drink_id))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_all_dishes_for_admin() -> List[dict]:
    """Все блюда кухни с категорией — для панели загрузки фото."""
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute(
        """
        SELECT d.id, d.name, d.photo_id, cat.name
        FROM dishes d
        JOIN categories cat ON d.category_id = cat.id
        ORDER BY cat.sort_order, cat.name, d.name
        """,
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "photo_id": r[2], "category_name": r[3]} for r in rows]


def get_all_drinks_for_admin() -> List[dict]:
    """Все напитки бара с категорией — для панели загрузки фото."""
    conn = sqlite3.connect(_MENU_DB)
    c = conn.cursor()
    c.execute(
        """
        SELECT d.id, d.name, d.photo_id, cat.name
        FROM drinks d
        JOIN categories cat ON d.category_id = cat.id
        ORDER BY cat.sort_order, cat.name, d.name
        """,
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "photo_id": r[2], "category_name": r[3]} for r in rows]
