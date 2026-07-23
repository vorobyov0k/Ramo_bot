"""
Маппинг должностей RAMO.
Должности (бизнесовые) отделены от ролей (технических).

Технические роли (user.role):
  • owner  — владелец (полные права, модерация)
  • admin  — админ бота (права на модерацию)
  • pm     — проект-менеджер бота (модерация)
  • manager— менеджер зала: управление задачами/контроль, БЕЗ модерации
  • user   — рядовой сотрудник

Должности (user.position) — для отображения и набора чек-листов:
  Бармен, Официант, Менеджер, Повар, … Техник
"""

# slug → (display_name, technical_role, checklists)
# Техническая роль: admin/pm/owner — модерация; user — рядовой сотрудник.
# Должность "Менеджер" — просто должность в зале, роль user (управление через должность, не через систему ролей).
POSITION_MAP = {
    "barman":      ("Бармен",             "user",    ["opening", "closing", "bar"]),
    "waiter":      ("Официант",           "user",    ["opening", "closing", "floor"]),
    "manager":     ("Менеджер",           "user",    ["opening", "closing", "bar", "floor", "cleaning", "kitchen"]),
    "cook":        ("Повар",              "user",    ["kitchen"]),
    "sous_chef":   ("Су-шеф",            "user",    ["kitchen"]),
    "chef":        ("Шеф-повар",         "user",    ["kitchen"]),
    "pm":          ("Проект. менеджер",  "pm",      ["opening", "closing", "bar", "floor", "cleaning", "kitchen"]),
    "bar_manager": ("Бар-менеджер",      "user",    ["opening", "closing", "bar", "floor"]),
    "cleaning":    ("Хозяюшка",          "user",    ["cleaning"]),
    "technician":  ("Техник",            "user",    ["opening", "closing"]),
    "owner":       ("Собственник",       "owner",   ["opening", "closing", "bar", "floor", "cleaning", "kitchen"]),
}

# Список должностей для выбора при регистрации
REGISTRATION_POSITIONS = [
    ("barman",      "🍺 Бармен"),
    ("waiter",      "🍽 Официант"),
    ("manager",     "👔 Менеджер"),
    ("cook",        "🥘 Повар"),
    ("sous_chef",   "🔪 Су-шеф"),
    ("chef",        "🍳 Шеф-повар"),
    ("bar_manager", "🍸 Бар-менеджер"),
    ("pm",          "📊 Проект. менеджер"),
    ("cleaning",    "🧹 Хозяюшка"),
    ("technician",  "🔧 Техник"),
    ("owner",       "👑 Собственник"),
]

# Должности для назначения через admin-панель (без owner — назначается отдельно)
ADMIN_POSITIONS = [
    ("barman",      "🍺 Бармен"),
    ("waiter",      "🍽 Официант"),
    ("manager",     "👔 Менеджер"),
    ("cook",        "🥘 Повар"),
    ("sous_chef",   "🔪 Су-шеф"),
    ("chef",        "🍳 Шеф-повар"),
    ("bar_manager", "🍸 Бар-менеджер"),
    ("pm",          "📊 Проект. менеджер"),
    ("cleaning",    "🧹 Хозяюшка"),
    ("technician",  "🔧 Техник"),
    ("owner",       "👑 Собственник"),
]

# Технические роли для назначения через admin-панель
# Менеджер — это ДОЛЖНОСТЬ (position: manager), а не роль. Роль всегда user/admin/pm/owner.
ADMIN_ROLES = [
    ("user",    "👤 Пользователь"),
    ("admin",   "🛡 Админ"),
    ("owner",   "👑 Владелец"),
]

# ── Роли с правами ────────────────────────────────────────────────────────
# MODERATOR_ROLES — доступ в РЕЖИМ МОДЕРАЦИИ (админ-панель: пользователи, роли,
#   рассылки, журналы, чек-листы, события). Это «права админа» в боте.
# (Менеджер — должность в зале, НЕ входит сюда; управление задачами/контролем
#  выполняется через должность, не через роль.)
MODERATOR_ROLES = {"admin", "pm", "owner"}

# MANAGER_ROLES — устаревшее имя, оставлено для совместимости. Совпадает с MODERATOR.
# Только admin/pm/owner имеют права. Обычные пользователи и должность "Менеджер"
# доступа в управление не получают.
MANAGER_ROLES = MODERATOR_ROLES

# Отображение технической роли в UI
ROLE_DISPLAY_UI = {
    "user":    "Пользователь",
    "owner":   "Владелец",
    "admin":   "Админ",
    "pm":      "Проект-менеджер",
}

# Обратная совместимость: старая роль → отображаемое имя (для пользователей без position)
ROLE_DISPLAY = {
    "pm":          "Проект. менеджер",
    "admin":       "Админ",
    "owner":       "Собственник",
    "barman":      "Бармен",
    "waiter":      "Официант",
    "security":    "Техник",        # legacy
    "technician":  "Техник",
    "cleaning":    "Хозяюшка",
    "cook":        "Повар",
    "sous_chef":   "Су-шеф",
    "chef":        "Шеф-повар",
    "user":        "Сотрудник",
    "other":       "Сотрудник",
}


def get_position_display(user) -> str:
    """Отображаемое имя должности пользователя."""
    if user and user.position and user.position in POSITION_MAP:
        return POSITION_MAP[user.position][0]
    if user:
        return ROLE_DISPLAY.get(user.role, user.role or "Сотрудник")
    return "Сотрудник"


def get_role_display_ui(role: str) -> str:
    """Отображаемое имя технической роли для UI."""
    return ROLE_DISPLAY_UI.get(role, role or "—")


def get_user_checklists(user) -> list:
    """Список типов чек-листов для пользователя (по должности, с фолбэком на роль)."""
    if user and user.position and user.position in POSITION_MAP:
        return list(POSITION_MAP[user.position][2])
    role = (user.role if user else "") or ""
    if role in {"admin", "manager", "pm", "owner"}:
        return ["opening", "closing", "bar", "floor", "cleaning", "kitchen"]
    elif role == "barman":
        return ["opening", "closing", "bar"]
    elif role == "waiter":
        return ["opening", "closing", "floor"]
    elif role == "cleaning":
        return ["cleaning"]
    elif role in {"cook", "chef", "sous_chef"}:
        return ["kitchen"]
    elif role in {"security", "technician"}:
        return ["opening", "closing"]
    return []


def position_to_role(position_slug: str) -> str:
    """Техническая роль для должности."""
    return POSITION_MAP.get(position_slug, ("", "user", []))[1]
