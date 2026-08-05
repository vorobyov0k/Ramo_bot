# RAMO Bot — Handoff для деплоя (для другой сессии)

**Прочитай этот файл первым, если тебя попросили задеплоить бота.**
**Дата составления**: 2026-07-30
**Ветка**: `main`
**Текущий HEAD**: `2d04d33` — Add category icons to library menu; expand home screen header

---

## ⚠️ ГЛАВНОЕ ПРАВИЛО: НЕ ТРОГАЙ `data/`

Вся живая информация (пользователи, бронирования, чек-листы, меню, фото, аудит-лог)
лежит в `data/*.db` и `data/cache/*.json`. Эти файлы:

- **НЕ отслеживаются git'ом** (см. `.gitignore`: `*.db`, `*.sqlite`, `data/cache/*.json`)
- **НЕ приходят и не изменяются через `git pull`** — это физически невозможно, раз они игнорируются
- Единственный способ их случайно снести — вручную удалить/перезаписать файл, либо
  скопировать поверх `data/` с другой машины/бэкапа

**Правило деплоя**: обновляем ТОЛЬКО код (`git pull`), `data/` на сервере не трогаем
вообще, ни при каких обстоятельствах, если явно не попросили восстановить из бэкапа.

Если на сервере уже есть рабочая `data/` (бот когда-то запускался и накопил реальные
данные) — она остаётся как есть. Если сервер девственный (первый деплой) — `data/`
создастся автоматически при первом старте бота (`init_db()` / `init_menu_db()`
создают таблицы и применяют миграции сами).

---

## Что нового с прошлого известного состояния (baseline `bdfd931`)

Диапазон `bdfd931..2d04d33` — 19 коммитов, вот что внутри:

### Код (файлы)
```
bot/handlers/admin.py             +492 строки  — журналы, аудит-лог, архивация
bot/handlers/onboarding.py        НОВЫЙ файл   — система адаптации новичков
bot/handlers/library.py           +52          — иконки категорий, вина-подменю
bot/handlers/menu.py              +94          — новый хедер, объединённые пункты меню
bot/handlers/task_manager.py      +69
bot/handlers/tasks.py             +17
bot/handlers/registration.py      +4           — фикс самоповышения прав (bdfd931)
bot/handlers/control.py           +8
bot/handlers/handover.py          +4
bot/main.py                       +13          — регистрация новых планировщиков
bot/states/forms.py               +38
bot/utils/db_connector.py         +437         — новые таблицы/колонки, CRUD
bot/utils/onboarding_content.py   НОВЫЙ файл
bot/utils/onboarding_scheduler.py НОВЫЙ файл
bot/utils/task_reminders.py       НОВЫЙ файл
bot/utils/cache_manager.py        +30
bot/utils/google_sheets_api.py    +26
bot/utils/menu_db.py              +6           — group_name для категорий
bot/utils/positions.py            +57          — SMM должность, группировка по отделам
bot/utils/promo_scheduler.py      +113
```

### Функционально это:
1. **Система онбординга** — трекинг стажёров по дням, мониторинг, напоминания
2. **Аудит-лог** — логирование действий (задачи/брони/рассылки/смены), архивация
3. **Меню бара** переструктурировано: 13 категорий вместо 18, подменю «Вина»
   → «Игристые/Белые/Красные», иконки у всех категорий (бар + кухня)
4. **Новый хедер** главного меню: отдел рядом с должностью, счётчик открытых
   чек-листов, объединённые пункты «Акции и события» / «Задачи и передача смены»
5. **SMM-должность**, группировка персонала по подразделениям в админке
6. **Фиксы**: самоповышение прав при регистрации (важный security-фикс, bdfd931),
   department никогда не проставлялся, su-шеф отсутствовал в рассылках,
   объём напитка не показывался в карточке

### requirements.txt — БЕЗ ИЗМЕНЕНИЙ
Новых pip-зависимостей нет, `pip install -r requirements.txt` можно пропустить,
если venv уже актуален с прошлого деплоя.

### .env — новая ОПЦИОНАЛЬНАЯ переменная
```
ONBOARDING_SHEET_NAME=OnboardingIncidents   # есть дефолт в коде, можно не добавлять
```
Ничего добавлять не обязательно — код подставит дефолт сам, если переменной нет.

---

## Миграции БД — все автоматические и безопасные

При старте бота `init_db()` (в `db_connector.py`) и `init_menu_db()` (в `menu_db.py`)
сами накатывают недостающие колонки через `ALTER TABLE ... ADD COLUMN`, обёрнутые
в `try/except` (если колонка уже есть — тихо пропускается). Полный список того,
что применится автоматически при первом старте новой версии кода:

```sql
-- bot_users
ALTER TABLE bot_users ADD COLUMN position VARCHAR(100)
ALTER TABLE bot_users ADD COLUMN requested_role VARCHAR(50)
ALTER TABLE bot_users ADD COLUMN timezone VARCHAR(50) DEFAULT 'Europe/Moscow'
ALTER TABLE bot_users ADD COLUMN mentor_id INTEGER REFERENCES bot_users(telegram_id)
ALTER TABLE bot_users ADD COLUMN hire_date DATETIME

-- handover_logs
ALTER TABLE handover_logs ADD COLUMN accepted_by INTEGER REFERENCES bot_users(telegram_id)
ALTER TABLE handover_logs ADD COLUMN accepted_at DATETIME

-- checklist_executions
ALTER TABLE checklist_executions ADD COLUMN archived BOOLEAN DEFAULT 0

-- incidents_reports
ALTER TABLE incidents_reports ADD COLUMN severity VARCHAR(20)
ALTER TABLE incidents_reports ADD COLUMN newcomer_id INTEGER REFERENCES bot_users(telegram_id)
ALTER TABLE incidents_reports ADD COLUMN onboarding_day INTEGER

-- onboarding_progress
ALTER TABLE onboarding_progress ADD COLUMN feedback_log JSON
ALTER TABLE onboarding_progress ADD COLUMN decision VARCHAR(20)

-- audit_logs
ALTER TABLE audit_logs ADD COLUMN archived BOOLEAN DEFAULT 0

-- categories (menu.db, отдельная БД)
ALTER TABLE categories ADD COLUMN group_name TEXT
ALTER TABLE dishes ADD COLUMN photo_id TEXT
ALTER TABLE drinks ADD COLUMN photo_id TEXT
```

**Ничего вручную запускать не нужно** — это всё срабатывает при обычном старте
`python main.py`. Единственное, что было запущено ВРУЧНУЮ один раз (уже применено
к обеим локальным копиям `data/menu.db`, но НЕ к серверной, если она отдельная) —
`scripts/merge_bar_categories.py`, который переносит напитки между категориями бара
(объединяет Кофе, Чаи, Пиво+сидр, группирует вина). Если на сервере СВОЯ, отдельная
`data/menu.db` с полным набором из 18 старых категорий — see раздел ниже.

---

## Пошаговый деплой

### Вариант А — сервер уже существует и на нём есть код + данные

```bash
# 1. Зайти на сервер, перейти в папку проекта
cd /path/to/ramo_bot

# 2. Остановить бота (посмотреть как запущен — systemd/screen/nohup)
# Пример для systemd:
sudo systemctl stop ramo-bot
# Пример для процесса в screen/nohup — найти и убить процесс:
ps aux | grep "python.*main.py"
kill <PID>

# 3. Убедиться что нет незакоммиченных изменений, которые перезатрутся
git status
# Если что-то есть и это не относится к data/ — СТОП, разберись сначала

# 4. Подтянуть новый код (ветка main)
git fetch origin
git checkout main
git pull origin main

# 5. Проверить требования (без изменений, но на всякий случай)
source venv/bin/activate
pip install -r requirements.txt

# 6. Запустить бота — миграции применятся автоматически на старте
python main.py
# или через systemd:
sudo systemctl start ramo-bot

# 7. Проверить логи на ошибки
tail -f bot.log   # или journalctl -u ramo-bot -f
```

### Вариант Б — первый деплой, сервера с ботом ещё не было

```bash
git clone git@gitlab.com:ramo_k-group1/ramo_bot.git
cd ramo_bot
git checkout main   # HEAD должен быть 2d04d33 или новее

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env — скопировать с локальной машины разработчика (там боевые токены)
# ВАЖНО: .env не в git, его нужно передать отдельно (не через открытый чат)

# data/ создастся автоматически при первом старте
python main.py
```

### Если на сервере старая `data/menu.db` (18 категорий бара, без group_name)

Категории и напитки останутся рабочими (старая структура не ломается новым кодом —
`group_name` просто будет `NULL` у всех, что равносильно «без группы»). НО тогда
не будет объединения Кофе/Чаи/Пиво-сидр и подменю «Вина». Если хочешь применить
и это — на сервере после деплоя кода выполни ОДИН раз:

```bash
python scripts/merge_bar_categories.py data/menu.db
```

Это идемпотентный скрипт (см. заголовок файла) — безопасно перезапускать,
повторный запуск на уже смёрженной БД ничего не ломает. **Сделай бэкап перед
первым запуском на боевой БД**:
```bash
cp data/menu.db data/menu.db.bak-$(date +%Y%m%d%H%M%S)
```

---

## Что НЕ было протестировано в проде

- Живая работа `onboarding_scheduler.py` / `task_reminders.py` (тестировалось
  только на dev-инстансе бота, не на реальном трафике)
- Реакция на серверный часовой пояс — весь код опирается на `Europe/Moscow`
  через `timezone(timedelta(hours=3))`, жёстко захардкожено. Убедись, что
  системное время сервера в UTC или что это не влияет (код сам конвертирует).

---

## Откат, если что-то сломалось

```bash
git log --oneline -25          # найти рабочий коммит до проблемы
git checkout <хеш>              # detached HEAD, временно
# или создать ветку:
git checkout -b rollback-temp <хеш>
python main.py
```

`data/` откату не подлежит и не должна — она независима от версии кода.
Если конкретно `menu.db` испортили скриптом — восстанови из
`data/menu.db.bak-*`, если бэкап делали (см. раздел выше).

---

## Контакты

Разработчик: Константин Воробьёв
Git: `origin` = GitLab (`git@gitlab.com:ramo_k-group1/ramo_bot.git`, основной),
`github` = GitHub (`git@github.com:vorobyov0k/Ramo_bot.git`, бэкап). Обе ветки
(`main`, `dev`) синхронизированы на момент составления документа.
