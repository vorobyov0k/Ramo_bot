"""
Applies the kitchen tech-card data to data/menu.db: composition (ingredients+grams)
for dishes where the source table Кухня Август Рамо.md gives explicit quantities.

Data provenance:
 - Matching: scripts/match_kitchen_menu.py (MATCHES dict).
 - Composition: ингредиент — вес, по строке на ингредиент, из техкарты.
 - Description: NOT touched — remains the serving-weight text already in DB.
 - The ~22 DB dishes with no source tech card are not touched (composition stays NULL).

Usage:
  python scripts/update_kitchen_menu_composition.py             # dry-run (default): prints diff, no writes
  python scripts/update_kitchen_menu_composition.py --apply      # writes, with a timestamped backup first
"""
import argparse
import shutil
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "data/menu.db"

# dish id -> new composition text (ингредиент — вес per line, joined with \n)
COMPOSITIONS = {
    40: "п/ф Бульон куриный — 350 г\nЛапша п/ф — 80 г\nКуриное филе су-вид п/ф — 70 г\nп/ф зелень — 2 г\nяйцо куриное — 1 шт",
    35: "Борщ п/ф новый — 300 г\nкартофель отварная п/ф — 40 г\nсметана — 30 г\nгорчица острая — 30 г\nп/ф чеснок зачищенный — 10 г\nСало / грудинка копченая — 30 г\nПампушки к борщу п/ф — 2 шт",
    36: "Щи п/ф — 300 г\nкартофель отварная п/ф — 40 г\nяйцо куриное — 1 шт\nсметана — 30 г\nп/ф зелень — 10 г",
    30: "Заправка для салата п/ф — 25 г\nкартофель п/ф — 60 г\nп/ф кинза — 5 г\nп/ф баклажан — 80 г\nпомидоры свежие п/ф — 90 г\nсыр творожный — 30 г\nсемечки тыквенные — 5 г\nподсолнечные — 5 г",
    31: "п/ф ростбиф — 50 г\nпомидоры черри — 30 г\nп/ф перец болгарский — 30 г\nкартофель беби — 60 г\nмикс семечек п/ф — 2 г\nЗаправка медово-горчичная п/ф — 10 г\nгорчичная п/ф — 10 г\nПесто петрушка п/ф — 20 г\nшпинат п/ф — 20 г",
    34: "Шпинат п/ф — 35 г\nп/ф тыква запеченная — 40 г\nСлива п/ф — 40 г\nПрошутто — 30 г\nсыр фета бривза — 25 г\nЗаправка медовая горчичная п/ф — 25 г",
    32: "Креветки п/ф — 70 г\nп/ф черри маринованный — 30 г\nЭдамаме — 30 г\nПерсик нектарин кг — 40 г\nЗаправка апельсиновая п/ф — 25 г\nшпинат п/ф — 25 г\nмикс семечек п/ф — 2 г",
    7: "Лепешка Роти — 1 шт\nп/ф форель х/к — 40 г\nп/ф микс салат — 10 г\nсоус Дзадзики п/ф — 50 г\nпомидоры черри — 20 г",
    42: "Стейк из капусты п/ф — 70 г\nп/ф индейка сувид — 80 г\nлисички — 50 г\nп/ф зелень — 10 г\nсоус с индейки п/ф — 45 г\nмасло зеленое п/ф — 0 г (следы)\nмикрозелень — 3 г",
    41: "п/ф пюре картофельное — 150 г\nКотлеты п/ф — 160 г\nОгурцы маринованные п/ф — 10 г\nСальса томатная п/ф — 15 г",
    43: "п/ф судак филе дефрост — 120 г\nБрокколи п/ф — 50 г\nЭдамаме — 20 г\nкартофель беби — 50 г\nмасло сливочное — 25 г\nПесто петрушка п/ф — 20 г\nсоль — 2 г\nСоус сливки белое вино п/ф — 50 г",
    46: "п/ф паста — 120 г\nПюре морковь п/ф — 70 г\nУтка томленая п/ф — 50 г\nмасло сливочное — 20 г\nсыр Пармезан — 15 г\nСыр Страчателла — 20 г\nп/ф черри маринованный — 15 г\nмикрозелень — 1 г",
    6: "Креветки п/ф — 60 г\nяйцо куриное — 2 шт\nсливки 33% — 30 г\nмасло сливочное — 30 г\nмасло растительное — 5 г\nшпинат п/ф — 20 г\nпомидоры черри — 30 г\nсоль — 1 г",
    23: "Сыр буратта — 1 шт (160 г)\nсалат к буратте п/ф — 130 г\nп/ф инжир — 5 г\nсемечки тыквенные — 2 г\nподсолнечные — 2 г",
    22: "Соус Вителло п/ф — 80 г\nп/ф ростбиф — 60 г\nмасло оливковое — 10 г\nмасло зеленое п/ф — 0 г (следы)",
    25: "сыр горгонзола — 30 г\nПрошутто — 30 г\nсыр козий — 30 г\nОливки п/ф — 30 г\nПерсик нектарин кг — 50 г\nмед — 10 г\nСлива п/ф — 50 г\nгруши п/ф — 20 г\nМакадамия орех — 30 г",
    21: "Тесто на пампушки п/ф — 50 г\nмасло сливочное — 10 г\nп/ф тар-тар говяжий — 95 г\nогурцы маринованные — 5 г\nсыр Пармезан — 10 г\nмасло зеленое п/ф — 2 г",
    8: "Тесто на пампушки п/ф — 140 г\nп/ф яйцо маринованное — 1 шт\nтунец сухой п/ф — 60 г\nзаправка медово-горчичная — 100 г\nмасло сливочное — 10 г\nсалат Айсберг п/ф — 20 г",
    9: "Тесто на пампушки п/ф — 140 г\nПесто петрушка п/ф — 15 г\nШпинат п/ф — 5 г\nОгурец маринованный п/ф — 10 г\nп/ф индейка сувид — 60 г\nСоус яблочный чесночный — 30 г",
    48: "Булочка для бургера — 1 шт\nфарш говяжий — 150 г\nСыр Чеддер — 45 г\nСоус медовый-яблоко п/ф — 60 г\nСалат Айсберг — 20 г\nЛуковый джем п/ф — 15 г\nОгурец маринованный п/ф — 20 г",
    5: "Сосиски — 150 г\nяйцо куриное — 2 шт\nТесто на пампушки п/ф — 100 г\nфасоль п/ф — 60 г\nбекон с/к — 40 г\nПомидоры свежие п/ф — 60 г\nшпинат п/ф — 10 г\nмасло сливочное — 10 г\nмасло растительное — 10 г",
    2: "Творожная основа п/ф — 150 г\nсметана — 50 г\nВаренье п/ф — 30 г\nкарамель п/ф — 10 г",
    4: "Тесто на пампушки п/ф — 60 г\nСкрембл п/ф — 110 г\nКреветки п/ф — 45 г\nСыр Страчателла — 30 г",
    1: "овсяные хлопья — 120 г\nмолоко без лактозы — 100 мл\nсоль — 1 г\nс/х сахар — 4 г\nп/ф тыква запеченная — 30 г\nСыр Страчателла — 20 г",
}

DB_UNMAPPED_IDS = [
    10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,  # Добавки (10 позиций)
    24, 26, 27, 28, 29, 33, 37, 38, 39, 40, 41, 43, 44, 45, 46, 47, 48,  # остальные без карт
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run diff only)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, composition FROM dishes ORDER BY id")
    current = {r[0]: {"name": r[1], "composition": r[2]} for r in cur.fetchall()}
    cur.execute("SELECT id FROM dishes")
    all_ids = {r[0] for r in cur.fetchall()}

    changes = []
    for dish_id, new_composition in COMPOSITIONS.items():
        if dish_id not in all_ids:
            print(f"!!! id={dish_id} not found in DB, skipping")
            continue
        old_composition = current.get(dish_id, {}).get("composition")
        if old_composition != new_composition:
            changes.append((dish_id, current.get(dish_id, {}).get("name", "?"), old_composition, new_composition))

    print(f"=== DRY-RUN DIFF ({len(changes)} of {len(COMPOSITIONS)} dishes change) ===\n")
    for dish_id, name, old_comp, new_comp in changes:
        print(f"id={dish_id} '{name}'")
        if old_comp != new_comp:
            print(f"  composition: {old_comp!r} → {new_comp!r}")
        print()

    print(f"DB unmapped (no tech card): {len(DB_UNMAPPED_IDS)} ids, composition stays NULL")

    if not args.apply:
        print("\nDry-run only, no changes written. Re-run with --apply to write.")
        conn.close()
        return

    backup_path = f"{DB_PATH}.bak-{time.strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(DB_PATH, backup_path)
    print(f"\nBackup written to {backup_path}")

    for dish_id, name, old_comp, new_comp in changes:
        cur.execute(
            "UPDATE dishes SET composition = ? WHERE id = ?",
            (new_comp, dish_id),
        )
    conn.commit()
    conn.close()
    print(f"Applied {len(changes)} updates to {DB_PATH}")


if __name__ == "__main__":
    main()
