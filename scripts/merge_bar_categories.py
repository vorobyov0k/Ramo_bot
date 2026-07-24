"""
Объединение категорий барного меню в data/menu.db.

- «Чёрный кофе» + «Кофе с молоком» → «Кофе»
- «Чаи» + «Сезонный спешл» → «Чаи»
- «На кране» + «Светлое пиво» + «Тёмное пиво» + «Сидры» → «Пиво и сидр»
  (напиток «Продрай Игристое вино» из «На кране» переносится в «Игристые вина»)
- «Игристые вина» / «Белые вина» / «Красные вина» помечаются group_name='Вина'
  (остаются отдельными категориями, но в клиентском меню схлопываются в подменю)

Идемпотентно — повторный запуск на уже смёрженной БД ничего не ломает.

Запуск:
    python scripts/merge_bar_categories.py <путь_к_menu.db> [<путь2> ...]
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")


def _category_id(cur, name: str):
    cur.execute("SELECT id FROM categories WHERE type='bar' AND name=?", (name,))
    row = cur.fetchone()
    return row[0] if row else None


def merge(db_path: str) -> None:
    print(f"\n=== {db_path} ===")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # На случай, если миграция ALTER TABLE ещё не применялась (init_menu_db
    # обычно накатывает её при старте бота).
    try:
        cur.execute("ALTER TABLE categories ADD COLUMN group_name TEXT")
    except sqlite3.OperationalError:
        pass

    # ── Кофе ─────────────────────────────────────────────────────────────
    black = _category_id(cur, "Чёрный кофе")
    milk = _category_id(cur, "Кофе с молоком")
    if black and milk:
        cur.execute("UPDATE drinks SET category_id=? WHERE category_id=?", (black, milk))
        cur.execute("UPDATE categories SET name='Кофе' WHERE id=?", (black,))
        cur.execute("DELETE FROM categories WHERE id=?", (milk,))
        print(f"  Кофе: слиты «Чёрный кофе»(id={black}) + «Кофе с молоком»(id={milk})")
    else:
        print("  Кофе: уже слито или категории не найдены — пропуск")

    # ── Чаи ──────────────────────────────────────────────────────────────
    tea = _category_id(cur, "Чаи")
    seasonal = _category_id(cur, "Сезонный спешл")
    if tea and seasonal:
        cur.execute("UPDATE drinks SET category_id=? WHERE category_id=?", (tea, seasonal))
        cur.execute("DELETE FROM categories WHERE id=?", (seasonal,))
        print(f"  Чаи: слиты «Чаи»(id={tea}) + «Сезонный спешл»(id={seasonal})")
    else:
        print("  Чаи: уже слито или категории не найдены — пропуск")

    # ── Пиво и сидр ──────────────────────────────────────────────────────
    tap = _category_id(cur, "На кране")
    light = _category_id(cur, "Светлое пиво")
    dark = _category_id(cur, "Тёмное пиво")
    ciders = _category_id(cur, "Сидры")
    sparkling_wine = _category_id(cur, "Игристые вина")
    if tap and (light or dark or ciders):
        if sparkling_wine:
            moved = cur.execute(
                "UPDATE drinks SET category_id=? WHERE category_id=? AND name LIKE '%вино%'",
                (sparkling_wine, tap),
            ).rowcount
            if moved:
                print(f"  Пиво и сидр: перенесено {moved} вин. позиций из «На кране» в «Игристые вина»")
        for cid in (light, dark, ciders):
            if cid:
                cur.execute("UPDATE drinks SET category_id=? WHERE category_id=?", (tap, cid))
        cur.execute("UPDATE categories SET name='Пиво и сидр' WHERE id=?", (tap,))
        for cid in (light, dark, ciders):
            if cid:
                cur.execute("DELETE FROM categories WHERE id=?", (cid,))
        print(f"  Пиво и сидр: слиты «На кране» + «Светлое» + «Тёмное» + «Сидры» → id={tap}")
    else:
        print("  Пиво и сидр: уже слито или категории не найдены — пропуск")

    # ── Вина: группировка по стилю (без слияния строк) ─────────────────────
    cur.execute(
        "UPDATE categories SET group_name='Вина' "
        "WHERE type='bar' AND name IN ('Игристые вина', 'Белые вина', 'Красные вина')"
    )
    print(f"  Вина: помечено группой 'Вина' — {cur.rowcount} категорий")

    # ── Порядок сортировки — перенумеровываем без дыр ──────────────────────
    cur.execute("SELECT id FROM categories WHERE type='bar' ORDER BY sort_order, name")
    for i, (cid,) in enumerate(cur.fetchall(), start=1):
        cur.execute("UPDATE categories SET sort_order=? WHERE id=?", (i, cid))

    conn.commit()

    cur.execute("SELECT name, group_name FROM categories WHERE type='bar' ORDER BY sort_order")
    print("  Итоговые категории бара:")
    for name, group in cur.fetchall():
        suffix = f"  [группа: {group}]" if group else ""
        print(f"    - {name}{suffix}")

    conn.close()


if __name__ == "__main__":
    paths = sys.argv[1:]
    if not paths:
        print("Укажи путь(и) к menu.db как аргументы командной строки.")
        sys.exit(1)
    for p in paths:
        merge(p)
