#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect("data/menu.db")
c = conn.cursor()

c.execute("""
    SELECT d.name, GROUP_CONCAT(a.name, ', ')
    FROM dishes d
    LEFT JOIN dish_allergens da ON d.id = da.dish_id
    LEFT JOIN allergens a ON da.allergen_id = a.id
    WHERE da.allergen_id IS NOT NULL
    GROUP BY d.id
""")

print("ITEMS WITH ALLERGENS:\n")
for name, allergens in c.fetchall():
    print(f"- {name}")
    print(f"  -> {allergens}\n")

conn.close()
