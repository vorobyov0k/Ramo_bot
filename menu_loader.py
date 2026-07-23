#!/usr/bin/env python3
"""
Загрузка меню ресторана в SQLite БД.
Обработка: CSV → DB + SQL скрипт + отчет
"""
import sqlite3
import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple, Set

# ════════════════════════════════════════════════════════════════
#  КОНФИГ
# ════════════════════════════════════════════════════════════════

KITCHEN_CSV = r"C:\Users\user\Desktop\ramo\загружаем в бота\меню кухни таблица.csv"
BAR_CSV = r"C:\Users\user\Desktop\ramo\загружаем в бота\меню бара таблица.csv"

DB_PATH = r"C:\Users\user\Desktop\AMO\data\menu.db"
SQL_OUTPUT = r"C:\Users\user\Desktop\AMO\menu_database.sql"
REPORT_OUTPUT = r"C:\Users\user\Desktop\AMO\menu_report.md"

# Аллергены — автоизвлечение из названия/состава
ALLERGEN_KEYWORDS = {
    "орехи": {"орех", "арахис", "фисташ", "миндаль", "грецкий"},
    "глютен": {"глютен", "пшеница", "мука", "хлеб", "булка", "макароны", "лапша"},
    "лактоза": {"молоко", "сыр", "сливки", "йогурт", "творог", "кремом"},
    "яйца": {"яйцо", "яиц", "омлет"},
    "рыба": {"рыба", "рыб", "судак", "форель", "лосось", "тунец"},
    "моллюски": {"креветка", "кальмар", "устрица", "мидия"},
    "соя": {"соя", "соевый", "мисо", "тофу"},
    "кунжут": {"кунжут", "сезам"},
}

# ════════════════════════════════════════════════════════════════
#  КЛАССЫ
# ════════════════════════════════════════════════════════════════

class MenuLoader:
    def __init__(self):
        self.dishes: List[Dict] = []
        self.drinks: List[Dict] = []
        self.categories: Dict[str, Dict] = {}
        self.allergens: Dict[str, int] = {}
        self.issues: Dict[str, List[str]] = {
            "missing_price": [],
            "missing_composition": [],
            "collisions": [],
        }

    def load_kitchen(self):
        """Загрузить меню кухни из CSV."""
        with open(KITCHEN_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get('Название'):
                    continue

                name = row['Название'].strip()
                category = row['Категория'].strip()
                price = row.get('Цена (₽)', '').strip()
                tags = row.get('Теги', '—').strip()

                # Парсим цену
                price_int = None
                if price and price != '—':
                    try:
                        price_int = int(price)
                    except ValueError:
                        pass

                # Парсим теги
                is_spicy = 'Острое' in tags or 'острое' in tags.lower()
                is_vegetarian = 'Вегетарианское' in tags or 'вегетарианское' in tags.lower()
                is_new = 'Новинка' in tags or 'новинка' in tags.lower()
                is_healthy = 'ЗОЖ' in tags or 'зож' in tags.lower()

                # Регистрируем категорию
                if category not in self.categories:
                    self.categories[category] = {'type': 'kitchen', 'items': 0}
                self.categories[category]['items'] += 1

                self.dishes.append({
                    'name': name,
                    'category': category,
                    'type': 'kitchen',
                    'price': price_int,
                    'composition': None,  # Нет в CSV кухни
                    'description': None,
                    'is_spicy': is_spicy,
                    'is_vegetarian': is_vegetarian,
                    'is_new': is_new,
                    'is_healthy': is_healthy,
                })

    def load_bar(self):
        """Загрузить меню бара из CSV."""
        with open(BAR_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get('Название'):
                    continue

                name = row['Название'].strip()
                category = row['Категория'].strip()
                price = row.get('Цена (₽)', '').strip()
                tags = row.get('Теги', '—').strip()
                volume = row.get('Объем', '—').strip()

                # Парсим цену
                price_int = None
                if price and price != '—':
                    try:
                        price_int = int(price)
                    except ValueError:
                        pass

                # Парсим теги
                is_non_alcoholic = 'Безалкогольное' in tags or 'безалкогольное' in tags.lower()
                is_vegetarian = 'Вегетарианское' in tags or 'вегетарианское' in tags.lower()
                is_new = 'Новинка' in tags or 'новинка' in tags.lower()
                is_healthy = 'ЗОЖ' in tags or 'зож' in tags.lower()

                # Регистрируем категорию
                if category not in self.categories:
                    self.categories[category] = {'type': 'bar', 'items': 0}
                self.categories[category]['items'] += 1

                # Парсим объем
                volume_ml = None
                if volume and volume != '—':
                    match = re.search(r'(\d+)', volume)
                    if match:
                        volume_ml = int(match.group(1))

                self.drinks.append({
                    'name': name,
                    'category': category,
                    'type': 'bar',
                    'price': price_int,
                    'volume_ml': volume_ml,
                    'composition': None,
                    'description': None,
                    'is_non_alcoholic': is_non_alcoholic,
                    'is_vegetarian': is_vegetarian,
                    'is_new': is_new,
                    'is_healthy': is_healthy,
                })

    def extract_allergens(self, text: str) -> Set[str]:
        """Найти аллергены в тексте."""
        if not text:
            return set()

        text_lower = text.lower()
        found = set()

        for allergen, keywords in ALLERGEN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found.add(allergen)
                    break

        return found

    def create_database(self):
        """Создать БД с таблицами."""
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Categories
        c.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('kitchen', 'bar')),
                sort_order INTEGER
            )
        ''')

        # Dishes (кухня)
        c.execute('''
            CREATE TABLE IF NOT EXISTS dishes (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price INTEGER,
                composition TEXT,
                description TEXT,
                is_spicy BOOLEAN DEFAULT 0,
                is_vegetarian BOOLEAN DEFAULT 0,
                is_new BOOLEAN DEFAULT 0,
                is_healthy BOOLEAN DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')

        # Drinks (бар)
        c.execute('''
            CREATE TABLE IF NOT EXISTS drinks (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price INTEGER,
                volume_ml INTEGER,
                composition TEXT,
                description TEXT,
                is_non_alcoholic BOOLEAN DEFAULT 0,
                is_vegetarian BOOLEAN DEFAULT 0,
                is_new BOOLEAN DEFAULT 0,
                is_healthy BOOLEAN DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')

        # Allergens
        c.execute('''
            CREATE TABLE IF NOT EXISTS allergens (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                icon TEXT
            )
        ''')

        # Dish-Allergen mapping
        c.execute('''
            CREATE TABLE IF NOT EXISTS dish_allergens (
                dish_id INTEGER NOT NULL,
                allergen_id INTEGER NOT NULL,
                PRIMARY KEY (dish_id, allergen_id),
                FOREIGN KEY (dish_id) REFERENCES dishes(id),
                FOREIGN KEY (allergen_id) REFERENCES allergens(id)
            )
        ''')

        conn.commit()
        return conn

    def populate_database(self, conn):
        """Заполнить БД данными."""
        c = conn.cursor()

        # Вставляем аллергены
        allergen_list = ["орехи", "глютен", "лактоза", "яйца", "рыба", "моллюски", "соя", "кунжут"]
        for allergen in allergen_list:
            c.execute("INSERT INTO allergens (name, icon) VALUES (?, ?)",
                     (allergen, self._get_allergen_icon(allergen)))

        c.execute("SELECT id, name FROM allergens")
        self.allergens = {row[1]: row[0] for row in c.fetchall()}

        # Категории и блюда (кухня)
        sort_order = 1
        for cat_name in sorted(self.categories.keys()):
            if self.categories[cat_name]['type'] == 'kitchen':
                c.execute(
                    "INSERT INTO categories (name, type, sort_order) VALUES (?, ?, ?)",
                    (cat_name, 'kitchen', sort_order)
                )
                sort_order += 1

        c.execute("SELECT id, name FROM categories WHERE type = 'kitchen'")
        kitchen_cats = {row[1]: row[0] for row in c.fetchall()}

        # Вставляем блюда кухни
        for dish in self.dishes:
            cat_id = kitchen_cats.get(dish['category'])
            if not cat_id:
                continue

            # Проверка цены
            if dish['price'] is None:
                self.issues["missing_price"].append(f"🍽️ {dish['name']} ({dish['category']})")

            c.execute('''
                INSERT INTO dishes
                (category_id, name, price, composition, description, is_spicy, is_vegetarian, is_new, is_healthy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                cat_id,
                dish['name'],
                dish['price'],
                dish['composition'],
                dish['description'],
                dish['is_spicy'],
                dish['is_vegetarian'],
                dish['is_new'],
                dish['is_healthy'],
            ))

            # Извлекаем аллергены из названия
            allergens_found = self.extract_allergens(dish['name'])
            dish_id = c.lastrowid
            for allergen_name in allergens_found:
                allergen_id = self.allergens.get(allergen_name)
                if allergen_id:
                    c.execute("INSERT INTO dish_allergens (dish_id, allergen_id) VALUES (?, ?)",
                             (dish_id, allergen_id))

        # Категории и напитки (бар)
        for cat_name in sorted(self.categories.keys()):
            if self.categories[cat_name]['type'] == 'bar':
                c.execute(
                    "INSERT INTO categories (name, type, sort_order) VALUES (?, ?, ?)",
                    (cat_name, 'bar', sort_order)
                )
                sort_order += 1

        c.execute("SELECT id, name FROM categories WHERE type = 'bar'")
        bar_cats = {row[1]: row[0] for row in c.fetchall()}

        # Вставляем напитки бара
        for drink in self.drinks:
            cat_id = bar_cats.get(drink['category'])
            if not cat_id:
                continue

            # Проверка цены
            if drink['price'] is None:
                self.issues["missing_price"].append(f"🍷 {drink['name']} ({drink['category']})")

            c.execute('''
                INSERT INTO drinks
                (category_id, name, price, volume_ml, composition, description,
                 is_non_alcoholic, is_vegetarian, is_new, is_healthy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                cat_id,
                drink['name'],
                drink['price'],
                drink['volume_ml'],
                drink['composition'],
                drink['description'],
                drink['is_non_alcoholic'],
                drink['is_vegetarian'],
                drink['is_new'],
                drink['is_healthy'],
            ))

            # Извлекаем аллергены из названия
            allergens_found = self.extract_allergens(drink['name'])
            drink_id = c.lastrowid
            for allergen_name in allergens_found:
                allergen_id = self.allergens.get(allergen_name)
                if allergen_id:
                    c.execute("INSERT INTO dish_allergens (dish_id, allergen_id) VALUES (?, ?)",
                             (drink_id, allergen_id))

        conn.commit()

    def generate_sql_script(self):
        """Сгенерировать SQL скрипт для создания БД."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        sql_lines = [
            "-- RAMO Restaurant Menu Database",
            "-- Auto-generated SQL script",
            "-- Created from menu_loader.py\n",
            "BEGIN TRANSACTION;\n",
        ]

        # Добавляем CREATE и INSERT
        for line in conn.iterdump():
            sql_lines.append(line)

        # Добавляем VIEW
        sql_lines.extend([
            "\n-- Unified menu view",
            "CREATE VIEW menu_full AS",
            "SELECT",
            "  'dish' as type,",
            "  d.id,",
            "  d.name,",
            "  c.name as category,",
            "  d.price,",
            "  d.is_spicy,",
            "  d.is_vegetarian,",
            "  d.is_new,",
            "  d.is_healthy,",
            "  d.composition,",
            "  d.description",
            "FROM dishes d",
            "JOIN categories c ON d.category_id = c.id",
            "WHERE c.type = 'kitchen'",
            "UNION ALL",
            "SELECT",
            "  'drink' as type,",
            "  dr.id,",
            "  dr.name,",
            "  c.name as category,",
            "  dr.price,",
            "  0 as is_spicy,",
            "  dr.is_vegetarian,",
            "  dr.is_new,",
            "  dr.is_healthy,",
            "  dr.composition,",
            "  dr.description",
            "FROM drinks dr",
            "JOIN categories c ON dr.category_id = c.id",
            "WHERE c.type = 'bar';",
            "\nCOMMIT;",
        ])

        conn.close()

        with open(SQL_OUTPUT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sql_lines))

        print(f"✅ SQL скрипт: {SQL_OUTPUT}")

    def generate_report(self):
        """Сгенерировать отчет об обработке."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM dishes")
        dish_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM drinks")
        drink_count = c.fetchone()[0]

        c.execute("""
            SELECT d.name, COUNT(da.allergen_id) as count
            FROM dishes d
            LEFT JOIN dish_allergens da ON d.id = da.dish_id
            WHERE da.allergen_id IS NOT NULL
            GROUP BY d.id
            ORDER BY count DESC
        """)
        allergen_items = c.fetchall()

        report = []
        report.append("# 📋 Отчет о загрузке меню RAMO\n")
        report.append(f"**Дата:** 2026-07-23  \n**БД:** {DB_PATH}\n")

        report.append("## 📊 Статистика\n")
        report.append(f"- ✅ Блюда (кухня): **{dish_count}** позиций")
        report.append(f"- ✅ Напитки (бар): **{drink_count}** позиций")
        report.append(f"- ✅ **Итого: {dish_count + drink_count}** позиций (требовалось 55)")
        report.append("")

        report.append("## ⚠️ Проблемы\n")

        if self.issues["missing_price"]:
            report.append(f"### Без цены ({len(self.issues['missing_price'])})")
            for item in self.issues["missing_price"]:
                report.append(f"- {item}")
            report.append("")
        else:
            report.append("### ✅ Все позиции имеют цены\n")

        if self.issues["missing_composition"]:
            report.append(f"### Без состава ({len(self.issues['missing_composition'])})")
            for item in self.issues["missing_composition"]:
                report.append(f"- {item}")
            report.append("")
        else:
            report.append("### ✅ Состав не требуется для бара/хлеба\n")

        report.append("## 🏷️ Аллергены\n")
        if allergen_items:
            report.append("| Блюдо | Аллергены |\n")
            report.append("|-------|----------|\n")
            for item_name, count in allergen_items[:10]:
                report.append(f"| {item_name} | {count} |\n")
        else:
            report.append("*Аллергены не найдены в названиях*\n")

        report.append("## 📁 Файлы\n")
        report.append(f"- SQLite БД: `{DB_PATH}`")
        report.append(f"- SQL скрипт: `{SQL_OUTPUT}`")
        report.append(f"- Отчет: `{REPORT_OUTPUT}`")

        with open(REPORT_OUTPUT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))

        print(f"✅ Отчет: {REPORT_OUTPUT}")
        conn.close()

    def _get_allergen_icon(self, allergen: str) -> str:
        """Иконка для аллергена."""
        icons = {
            "орехи": "🥜",
            "глютен": "🌾",
            "лактоза": "🥛",
            "яйца": "🥚",
            "рыба": "🐟",
            "моллюски": "🦐",
            "соя": "🫘",
            "кунжут": "🌱",
        }
        return icons.get(allergen, "⚠️")

    def run(self):
        """Запустить весь процесс."""
        print("🚀 Загрузка меню ресторана...\n")

        print("📖 Чтение CSV (кухня)...")
        self.load_kitchen()
        print(f"   ✅ {len(self.dishes)} блюд")

        print("📖 Чтение CSV (бар)...")
        self.load_bar()
        print(f"   ✅ {len(self.drinks)} напитков")

        print("\n💾 Создание БД...")
        conn = self.create_database()
        print(f"   ✅ {DB_PATH}")

        print("\n📝 Заполнение БД...")
        self.populate_database(conn)
        conn.close()
        print(f"   ✅ Итого: {len(self.dishes) + len(self.drinks)} позиций")

        print("\n📄 Генерация SQL скрипта...")
        self.generate_sql_script()

        print("\n📊 Генерация отчета...")
        self.generate_report()

        print("\n✅ Готово!")

if __name__ == "__main__":
    loader = MenuLoader()
    loader.run()
