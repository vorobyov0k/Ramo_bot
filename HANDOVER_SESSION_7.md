# HANDOVER — Сессия 7

**Дата:** 2026-07-23  
**Статус:** Завершена  
**Ветка:** main (без git)

---

## Что было сделано

### 1. Завершение Task 6 из сессии 6 — разделение ролей и должностей

**Файлы:** `bot/handlers/tasks.py`, `bot/handlers/task_manager.py`

- `tasks_menu` — чек-листы теперь строятся через `get_user_checklists(user)` вместо if/elif по ролям
- Менеджеры автоматически получают все 6 чек-листов (opening/closing/bar/floor/cleaning/kitchen)
- В `task_manager.py`: при выборе исполнителя задачи показывается `position_display` вместо `dept_label`
- Импорт `get_position_display` добавлен в `task_manager.py`

---

### 2. Персистентность прогресса чек-листов

**Файл:** `bot/handlers/tasks.py`

**Проблема:** При уходе из чек-листа в меню и возврате все галочки сбрасывались.

**Решение — in-memory словарь `_PROGRESS`:**
```python
_PROGRESS: dict[tuple[int, str], set] = {}
```
- Ключ: `(telegram_id, cl_type)` — уникален на пользователя и тип чек-листа
- При каждом toggle → `_prog_set()` сохраняет прогресс
- При открытии чек-листа → `_prog_get()` загружает сохранённое состояние
- После `submit` → `_prog_clear()` сбрасывает прогресс для этого чек-листа
- Прогресс переживает навигацию по меню, **не** переживает рестарт бота (это ок для посменной работы)

**Бонус:** В меню задач кнопки чек-листов показывают прогресс: `🌅 Открытие (3/12)`

---

### 3. Передача смены — переработка

**Файлы:** `bot/handlers/handover.py`, `bot/utils/db_connector.py`

#### DB — новые поля и функции:
- `HandoverLog.accepted_by` (Integer, nullable FK)
- `HandoverLog.accepted_at` (DateTime, nullable)
- Миграция ALTER TABLE при `init_db()`
- `get_last_handover()` — самая свежая запись
- `accept_handover(handover_id, user_id)` — помечает как принятую

#### Меню передачи смены:
- Показывает **последнюю передачу**: дата, важность, статус принятия, превью текста (300 символов)
- Кнопка **«✅ Принять смену»** — видна только если передача ещё не принята
- После принятия кнопка исчезает, показывается «Принял(а): Имя (Должность)»

#### Навигация — исправлена:
- Все кнопки «← Назад» в FSM-форме возвращают в меню передачи (не на главную)
- После сохранения → сразу показывается обновлённое меню передачи с новой записью
- Отмена → тоже меню передачи

---

### 4. Система должностей и ролей — финальная структура

**Файлы:** `bot/utils/positions.py`, `bot/utils/db_connector.py`, `bot/handlers/admin.py`, `bot/handlers/library.py`, `bot/utils/cache_manager.py`, `bot/keyboards/inline_buttons.py`, `bot/states/forms.py`

#### Технические роли (права доступа):
| Роль | Права |
|------|-------|
| `user` | Пользовательский режим |
| `manager` | Режим модерации |
| `owner` | = manager (расширения отложены) |
| `admin`, `pm` | Legacy — продолжают работать |

#### Должности (9 + owner):
| Slug | Название | Роль | Чек-листы |
|------|----------|------|-----------|
| `barman` | Бармен | user | opening, closing, bar |
| `waiter` | Официант | user | opening, closing, floor |
| `cook` | Повар | user | kitchen |
| `sous_chef` | Су-шеф | user | kitchen |
| `chef` | Шеф-повар | manager | kitchen |
| `pm` | Проект. менеджер | manager | все |
| `bar_manager` | Бар-менеджер | manager | opening, closing, bar, floor |
| `cleaning` | Хозяюшка | user | cleaning |
| `technician` | Техник | user | opening, closing |
| `owner` | Собственник | owner | все |

#### Удалена должность «Охранник» (`security`):
- Заменена на «Техник» (`technician`)
- Миграция при старте: `role=security` → `role=user, position=technician`
- Новый контент «Техник» добавлен в `cache_manager.py` и `library.py`

#### Новые функции в `positions.py`:
- `ADMIN_ROLES` — список ролей для admin-панели (user/manager/owner)
- `ADMIN_POSITIONS` — список должностей для admin-панели (все 10)
- `get_role_display_ui(role)` — отображаемое название роли для UI
- `REGISTRATION_POSITIONS` расширен (добавлены sous_chef, technician)

#### `IsModerator` обновлён:
```python
db_user.role in {"admin", "pm", "manager", "owner"}
```

---

### 5. Режим модерации — раздел «Пользователи»

**Файл:** `bot/handlers/admin.py`

#### Список пользователей:
- **До:** показывал роль (`manager`/`user`)
- **После:** показывает должность (`Бармен — Иван Петров`)
- Кнопка **«🔍 Фильтр ▼»** → выбор фильтра:
  - По должности (все 10 вариантов)
  - По роли (Пользователь / Менеджер / Владелец)

#### Карточка сотрудника:
```
👤 Имя
💼 Должность: Бармен
🎭 Роль: Пользователь
📁 Статус: Активен
📅 Регистрация: 01.01.2026
```

Кнопки:
- **✏️ Изменить роль** → выбор роли → подтверждение → сохранение + уведомление сотруднику
- **✏️ Назначить должность** → выбор должности → подтверждение → сохранение + уведомление
- **🚫 Заблокировать** (без изменений)

Flow без FSM: всё через callback_data:
```
admin:user_role:{id} → admin:role_confirm:{id}:{role} → admin:set_role:{id}:{role}
admin:user_pos:{id}  → admin:pos_confirm:{id}:{pos}   → admin:set_pos:{id}:{pos}
```

#### Рассылка — обновлены цели:
- Убрана «Охрана», добавлены: Повара, Шеф-повара, Бар-менеджеры, Хозяюшки, Техники
- Фильтрация по `position`, а для роли-менеджер — по `role in {"manager","admin","pm","owner"}`

---

### 6. Библиотека — Су-шеф и Техник

**Файл:** `bot/handlers/library.py`

- Добавлены кнопки «🔪 Су-шеф» и «🔧 Техник» в меню должностей
- Убрана кнопка «Адм. смены» (устаревшая роль manager без позиции)
- Должности теперь в сетке 2×N для компактности

---

### 7. FAQ — разбивка на кнопки

**Файл:** `bot/handlers/library.py`

**До:** один длинный текст со всеми 8 Q&A.

**После:** 
- Меню FAQ → 8 кнопок (каждая = вопрос, до 55 символов)
- Клик → карточка: вопрос жирным + ответ + счётчик `1/8`
- Навигация «← Пред.» / «След. →» между вопросами
- «← К списку вопросов» возвращает в меню FAQ

Callback-паттерн: `lib:faq:{index}`

---

## Текущее состояние системы

### Технический стек
- aiogram v3, SQLite + SQLAlchemy async (aiosqlite)
- FSM для регистрации, передачи смены, инцидентов, создания задач
- In-memory кэш прогресса чек-листов

### Архитектурные принципы
- `User.role` — технические права (user/manager/owner + legacy admin/pm)
- `User.position` — slug должности (barman, waiter, sous_chef, technician, ...)
- Все UI-отображения через `get_position_display(user)` и `get_role_display_ui(role)`
- Callback separator `_s_` для кодирования `role_key + section_id` в одной строке

### Структура callback_data
```
lib:role_{slug}           — карточка должности (список секций)
lib:role_{slug}_s_{sec}   — конкретная секция должности
lib:faq:{index}           — конкретный FAQ-вопрос
lib:reg_{id}_s_{sub_id}   — подраздел регламента
admin:user:{id}           — карточка пользователя
admin:user_role:{id}      — выбор новой роли
admin:role_confirm:{id}:{role} — подтверждение смены роли
admin:set_role:{id}:{role}     — применить смену роли
admin:user_pos:{id}       — выбор новой должности
admin:pos_confirm:{id}:{pos}   — подтверждение смены должности
admin:set_pos:{id}:{pos}       — применить смену должности
admin:users_pos:{slug}    — список: фильтр по должности
admin:users_role:{role}   — список: фильтр по роли
handover:accept:{id}      — принять передачу смены
home:start_shift          — начать смену
home:end_shift            — закрыть смену
```

---

## Что осталось / возможные следующие шаги

- [ ] Контент для «Су-шеф» в `positions._SEED` — секции info/zones/kpi/forbidden/rules (добавлен в эту сессию)
- [ ] Контент для «Техник» в чек-листах opening/closing (технические пункты, без барных/заловых)
- [ ] Фото к блюдам и инструкциям (задача из сессии 6, не тронута)
- [ ] Поле `description` для позиций меню (задача из сессии 6, не тронута)
- [ ] Онбординг-прогресс (`menu:progress`) — раздел задекларирован, контент пустой
- [ ] Аттестационный модуль (упоминается в онбординге)
- [ ] Отчётность для `owner` роли
- [ ] Тесты для новых хендлеров

---

## Ключевые файлы сессии

| Файл | Что изменилось |
|------|----------------|
| `bot/utils/positions.py` | Полная переработка: 10 должностей, ADMIN_ROLES, ADMIN_POSITIONS, get_role_display_ui |
| `bot/utils/db_connector.py` | HandoverLog.accepted_by/at, get_last_handover, accept_handover, update_user_position, миграция security→technician |
| `bot/handlers/admin.py` | Список с должностями + фильтры, карточка с двумя кнопками управления, flow смены роли/должности |
| `bot/handlers/handover.py` | Полная переработка: просмотр последней передачи, «Принять смену», исправлена навигация |
| `bot/handlers/tasks.py` | Персистентность прогресса чек-листов (_PROGRESS dict), индикатор в меню |
| `bot/handlers/task_manager.py` | position_display в списке исполнителей |
| `bot/handlers/library.py` | Су-шеф + Техник в меню должностей, FAQ → кнопки по пунктам |
| `bot/utils/cache_manager.py` | security → technician (контент Техника), добавлен Су-шеф |
| `bot/keyboards/inline_buttons.py` | Регистрация — кнопки из REGISTRATION_POSITIONS (динамически) |
| `bot/states/forms.py` | AdminEditPositionState добавлен |
