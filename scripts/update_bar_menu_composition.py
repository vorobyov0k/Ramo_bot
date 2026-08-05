"""
Applies the August bar-menu update to data/menu.db: composition (ingredients+grams,
only where the source table actually gives quantities) and description (taste-profile
lines authored by the bar subagent) for the 72 matched drinks.

Data provenance:
 - Matching: scripts/match_bar_menu.py (MATCHES dict, reviewed with the user).
 - Composition: only built for drinks where барное меню август Рамо.md gives explicit
   gram/ml amounts (coffee, hot drinks, iced-tea specials — ~14 items). Everywhere else
   the source table only lists ingredient names with no quantity, so composition is
   cleared to NULL (fixes the pre-existing bug where some rows held price/volume text
   instead of ingredients) and left for staff to fill in via the new admin editor
   (bot/handlers/admin.py, "✏️ Редактировать состав").
 - Description: taste-profile phrases from the bar subagent, one batch per menu section.
 - The 5 DB drinks with no source-table counterpart (ids 31, 41, 59, 60, 65) are not
   touched by this script at all — flagged separately for Taras/bar team review.

Usage:
  python scripts/update_bar_menu_composition.py             # dry-run (default): prints diff, no writes
  python scripts/update_bar_menu_composition.py --apply      # writes, with a timestamped backup first
"""
import argparse
import shutil
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "data/menu.db"

# drink id -> new composition text (<pre> table rows joined with \n), only for the
# ~14 items where the source table gives explicit gram/ml amounts.
COMPOSITIONS = {
    1: "Кофе в зёрнах — 20 г",
    2: "Кофе в зёрнах — 10/20 г\nКипяток — по объёму",
    3: "Кофе в зёрнах — 10/20 г\nМолоко — по объёму",
    4: "Кофе в зёрнах — 10 г\nМолоко — по объёму",
    5: "Кофе в зёрнах — 20 г\nМолоко — по объёму",
    6: "Кофе в зёрнах — 10 г\nСливки — по объёму",
    7: "Сливки 10-11% — 20 г\nЭспрессо — 1 порция\nТоник — по объёму",
    8: "Сок красного апельсина — 20 мл\nЭспрессо — 1 порция\nЛёд — по объёму",
    9: "Альтернативное молоко — +10 г (замена коровьего)",
    18: "Вода — 100 мл\nПюре гуавы — по вкусу\nРозовый сироп — по вкусу",
    19: "Вода — 100 мл\nСироп малины — 40 мл\nЛаванда — по вкусу\nЛимон — по вкусу",
    20: "Вода — 150 мл\nПюре манго-маракуйя — по вкусу\nСахарный сироп — по вкусу",
    21: "Какао-порошок — 10/15 г\nМолоко — 200/300 мл",
}

# drink id -> new taste-profile description (bar subagent output, one batch per section)
DESCRIPTIONS = {
    1: "Крепкий, насыщенный, с горчинкой.",
    2: "Чистый и мягкий, менее крепкий.",
    3: "Кофейный с нежной молочной пенкой.",
    4: "Мягкий, молочный, с лёгким кофе.",
    5: "Плотный, кофейный, чуть крепче латте.",
    6: "Сливочный, нежный, слегка сладковатый.",
    7: "Освежающий, цитрусовый, с горчинкой.",
    8: "Цитрусовый, кисло-сладкий, освежающий.",
    9: "Растительный оттенок к любимому кофе.",
    21: "Шоколадный, тёплый, сладкий.",
    22: "Сливочно-банановый с травяной ноткой матчи.",
    10: "Насыщенный, солодовый, с терпкостью.",
    11: "Мягкий травянистый с лёгкой сладостью.",
    12: "Мягкий медово-травяной, без горечи.",
    13: "Нежный цветочный с зелёной свежестью.",
    14: "Мягкий травяной, ароматный.",
    15: "Лёгкий, нежный, чуть сладковатый.",
    16: "Сливочный, мягкий, с молочными нотами.",
    17: "Цитрусовый бергамот на чёрной основе.",
    18: "Сладко-цветочный с тропической гуавой.",
    19: "Ягодный с цветочной лавандой и кислинкой.",
    20: "Тропический манго-маракуйя, сладкий с кислинкой.",
    23: "Сладкий, свежий, с цитрусовой кислинкой.",
    24: "Чистый нейтральный вкус, без сладости.",
    25: "Натуральный фруктовый, в ассортименте.",
    26: "Сладкий, карамельный, с игристой остротой.",
    27: "Тропический, сладкий с кислинкой маракуйи.",
    28: "Ягодный, пряный, с травяной свежестью.",
    29: "Сладкий, тропический, с цветочным личи.",
    30: "Мягкий, сливочно-грушевый, с травяным оттенком.",
    32: "Мягкий солодовый с лёгкой хмелевой горчинкой.",
    33: "Солодовый, мягкий, с хлебной ноткой.",
    34: "Хмелевой, цитрусово-травяной, с приятной горчинкой.",
    35: "Сладкая вишня с лёгкой кислинкой.",
    36: "Тёмный, с нотами кофе и жжёного солода.",
    37: "Ягодный, свежий, кисло-сладкий.",
    38: "Сладкий, сочный, с грушевым ароматом.",
    39: "Ягодный, мягкий, слегка сладкий.",
    40: "Сладкий грушевый, сочный и лёгкий.",
    42: "Сухой, освежающий, с цитрусовой кислинкой.",
    43: "Лёгкий, фруктовый, с нотами груши и яблока.",
    44: "Строгий, сухой, с минеральной цитрусовой ноткой.",
    45: "Свежий, травянисто-цитрусовый, с яркой кислинкой.",
    46: "Ароматный, яблочно-цитрусовый, с живой кислинкой.",
    47: "Яркий, тропический, с крыжовником и цитрусом.",
    48: "Мягкий, сливово-вишнёвый, с бархатными танинами.",
    49: "Насыщенный, тёмно-ягодный, с лёгкой пряностью.",
    50: "Терпкий, вишнёвый, с кисло-пряным характером.",
    51: "Свежий, слегка сладковатый, с чистым мягким финишем.",
    52: "Тёплый, с нотами дуба, карамели и дымка.",
    53: "Чистая, мягкая, с округлым нейтральным телом.",
    54: "Насыщенный, с тонами сухофруктов, дуба и ванили.",
    55: "Мягкий, сладковатый, с нотами карамели и ванили.",
    56: "Сухой, свежий, с ярким хвойным акцентом можжевельника.",
    57: "Яркая, землистая, с дымком и перечной остринкой.",
    58: "Тропический сливочный с маракуйей.",
    61: "Солёная карамель с цитрусовой кислинкой.",
    62: "Миндально-персиковый, кисло-сладкий.",
    63: "Игристый, цитрусовый с лёгкой горчинкой.",
    64: "Ягодный, кисло-сладкий, освежающий.",
    66: "Вишнёво-пряный с кислинкой и горчинкой.",
    67: "Горько-сладкий, ягодный.",
    68: "Кисло-сладкий, с бархатной пенкой.",
    69: "Свежий, яблочно-травяной.",
    70: "Яркий цитрус, сладко-лимонный.",
    71: "Тропический, с зелёной терпкостью фейхоа.",
    72: "Сливочный, десертный, клубника со сдобой.",
    73: "Ягодный с травяной свежестью.",
    74: "Сливочный, мягкий, спелый банан.",
    75: "Цитрусовый с пряной остринкой.",
    76: "Ассорти вкусов, маленькие порции для дегустации.",
    77: "Полное ассорти всех настоек, полные порции.",
}

DB_ORPHAN_IDS = [31, 41, 59, 60, 65]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run diff only)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, composition, description FROM drinks")
    current = {r[0]: {"name": r[1], "composition": r[2], "description": r[3]} for r in cur.fetchall()}

    all_matched_ids = sorted(set(DESCRIPTIONS.keys()))
    changes = []
    for drink_id in all_matched_ids:
        row = current.get(drink_id)
        if row is None:
            print(f"!!! id={drink_id} not found in DB, skipping")
            continue
        new_composition = COMPOSITIONS.get(drink_id)  # None if no grams -> clear field
        new_description = DESCRIPTIONS[drink_id]
        if row["composition"] != new_composition or row["description"] != new_description:
            changes.append((drink_id, row, new_composition, new_description))

    print(f"=== DRY-RUN DIFF ({len(changes)} of {len(all_matched_ids)} matched drinks change) ===\n")
    for drink_id, row, new_comp, new_desc in changes:
        print(f"id={drink_id} '{row['name']}'")
        if row["composition"] != new_comp:
            print(f"  composition: {row['composition']!r} -> {new_comp!r}")
        if row["description"] != new_desc:
            print(f"  description: {row['description']!r} -> {new_desc!r}")
        print()

    print(f"DB orphans (untouched, no source-table match): {DB_ORPHAN_IDS}")
    unaccounted = set(current.keys()) - set(all_matched_ids) - set(DB_ORPHAN_IDS)
    if unaccounted:
        print(f"!!! UNACCOUNTED ids (not in DESCRIPTIONS, not orphans) — investigate: {sorted(unaccounted)}")

    if not args.apply:
        print("\nDry-run only, no changes written. Re-run with --apply to write.")
        conn.close()
        return

    backup_path = f"{DB_PATH}.bak-{time.strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(DB_PATH, backup_path)
    print(f"\nBackup written to {backup_path}")

    for drink_id, row, new_comp, new_desc in changes:
        cur.execute(
            "UPDATE drinks SET composition = ?, description = ? WHERE id = ?",
            (new_comp, new_desc, drink_id),
        )
    conn.commit()
    conn.close()
    print(f"Applied {len(changes)} updates to {DB_PATH}")


if __name__ == "__main__":
    main()
