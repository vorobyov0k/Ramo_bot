#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect("data/menu.db")
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM dishes")
dishes = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM drinks")
drinks = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM dishes WHERE is_spicy = 1")
spicy = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM dishes WHERE is_vegetarian = 1")
vegetarian = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM dishes WHERE is_new = 1")
new_dishes = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM drinks WHERE is_non_alcoholic = 1")
non_alc = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM dish_allergens")
allergen_links = c.fetchone()[0]

print("DATABASE VERIFICATION")
print(f"Dishes: {dishes}")
print(f"Drinks: {drinks}")
print(f"Total: {dishes + drinks}")
print()
print("TAGS:")
print(f"Spicy: {spicy}")
print(f"Vegetarian: {vegetarian}")
print(f"New: {new_dishes}")
print(f"Non-alcoholic: {non_alc}")
print()
print(f"Allergen links: {allergen_links}")

conn.close()
