---
date: 2026-08-03
tag: DEPLOYMENT_6_PATCHES
status: ✅ успешно развёрнут на продакшене
---

# Сессия 03-08 — Деплой 6 правок RAMO-бота

## ✅ Что сделано

### 1. Реализация всех 6 правок в коде (AMO-dev, ветка dev)

**Правка 1: Меню**
- Заменена кнопка `🎁 Акции и события` на `📅 События`
- Добавлена кнопка `🎁 Акции` в подменю событий
- `promos_today()` слушает оба callback'а: `menu:promos` и `events:promos`
- Файлы: `bot/handlers/menu.py`, `bot/handlers/events.py`, `bot/handlers/promos.py`

**Правка 2: Чек-листы**
- Убрана кнопка из главного меню библиотеки
- Добавлена в карточку должности (позиции)
- Новый хендлер `checklists_by_role()` использует `POSITION_MAP` из `positions.py`
- Динамический "назад" в `checklist_view()` — возвращает на карточку должности
- Файл: `bot/handlers/library.py` + импорт `POSITION_MAP`

**Правка 3: Контакты**
- Заменён динамический текст из кэша на статичный
- Адрес, телефон, социальные сети, режим работы, философия бренда
- Файл: `bot/handlers/library.py`

**Правка 4: Погода** ⭐ АКТИВНА
- Новые функции: `do_weather_check()` и `weather_loop()`
- Импорт `get_current_weather()` из `task_reminders.py` (Open-Meteo API, нет ключа)
- Интервал: 5 минут (asyncio.sleep(300))
- Условие срабатывания: |Δt| ≥ 1.5°C
- Рассылка: `get_users_on_shift()` (только сотрудники на смене)
- Регистрация в `main.py`: `asyncio.create_task(promo_scheduler.weather_loop(bot))`
- Файлы: `bot/utils/promo_scheduler.py`, `bot/main.py`

**Правка 5: Рабочие события** ⭐ АКТИВНА
- Новая колонка `participants = Column(JSON, default=list)` в модели `Event`
- Новый FSM `EventAddWorkEventState` с 4 шагами: title → description → date → participants
- Мультивыбор участников: toggle UI (☑️/⬜) + re-render по образцу `onboarding.py`
- Рассылка уведомлений участникам при создании события
- Файлы: `bot/utils/db_connector.py` (модель + миграция), `bot/states/forms.py`, `bot/handlers/events.py`

**Правка 6: Расширение прав задач** ⭐ АКТИВНА
- Новая колонка `assigned_role = Column(String(20), nullable=True)` в модели `Task`
- Новая функция `get_assignable_users(creator_role, department)` для фильтрации по ролям:
  - owner/pm: все активные пользователи
  - admin: все кроме owner/pm (+ опциональный фильтр по department)
  - user: кроме admin/pm/owner
- Новая кнопка "📢 Всем админам" для owner/pm
- Новый хендлер `tc_all_admins()` на `F.data == "tmc:all_admins"`
- Расширена логика `is_assignee` в карточке задачи: `task.assigned_to == user.telegram_id or (task.assigned_to is None and task.assigned_role == user.role)`
- Обновлены все вызовы `get_tasks_for_worker()` и `get_today_open_tasks_count()` с параметром `role=user.role`
- Файлы: `bot/utils/db_connector.py`, `bot/handlers/task_manager.py`, `bot/handlers/menu.py`

### 2. Пуш кода в GitLab

Commit: `9bcf9d3` в `origin/dev`
```
Implement 6 feature patches for RAMO bot
- Правка 1: Меню Events
- Правка 2: Чек-листы в должностях
- Правка 3: Контакты (статичный текст)
- Правка 4: Погода (5 мин интервал, Δt≥1.5°C)
- Правка 5: Рабочие события (участники + FSM)
- Правка 6: Задачи (расширенные права, Всем админам)
```

### 3. Деплой на продакшен (89.58.17.123:/opt/ramo_bot)

**Процесс:**
- Бэкап старой версии: `/opt/ramo_bot.backup.1722693600`
- Копирование 9 обновлённых файлов через SCP (PowerShell)
- Kill старого процесса (PID 34868)
- Запуск нового процесса: `/opt/ramo_bot/venv/bin/python main.py`

**Результат:**
```
✅ База данных готова
✅ Кэш инициализирован
✅ Планировщик брифа и пересменки запущен
✅ Планировщик погоды запущен (интервал 5 мин)  ← НОВОЕ
✅ Планировщик онбординга запущен
✅ Планировщик рекомендаций по отделам запущен
✅ Команды бота установлены
✅ Start polling
```

**Текущее состояние (2026-08-04 13:57:22):**
```
root      108651  4.9  3.1 286688 127484 pts/0   Sl   13:57   0:01 /opt/ramo_bot/venv/bin/python main.py
```

## 📋 Готовые артефакты

- ✅ Весь код на `origin/dev` (commit 9bcf9d3)
- ✅ Миграции БД применены автоматически через `init_db()` (ALTER TABLE pattern, backward-compatible)
- ✅ Бот запущен на production

## 🚀 Следующие шаги

### Если нужно перезагрузить бот на production:
```bash
ssh root@89.58.17.123

# На сервере:
kill $(pgrep -f "python main.py")
sleep 2
cd /opt/ramo_bot && /opt/ramo_bot/venv/bin/python main.py &
sleep 3
ps aux | grep "python main.py" | grep -v grep
```

### Если нужно обновить код:
```bash
# На локальной машине (PowerShell):
cd C:\Users\user\Desktop\AMO-dev
git fetch origin dev
git pull origin dev

# Копируем обновлённые файлы на server через SCP:
$SERVER = "root@89.58.17.123"
$BOT_PATH = "/opt/ramo_bot"

scp bot/handlers/events.py ${SERVER}:${BOT_PATH}/bot/handlers/
scp bot/handlers/library.py ${SERVER}:${BOT_PATH}/bot/handlers/
scp bot/handlers/menu.py ${SERVER}:${BOT_PATH}/bot/handlers/
scp bot/handlers/promos.py ${SERVER}:${BOT_PATH}/bot/handlers/
scp bot/handlers/task_manager.py ${SERVER}:${BOT_PATH}/bot/handlers/
scp bot/main.py ${SERVER}:${BOT_PATH}/
scp bot/states/forms.py ${SERVER}:${BOT_PATH}/bot/states/
scp bot/utils/db_connector.py ${SERVER}:${BOT_PATH}/bot/utils/
scp bot/utils/promo_scheduler.py ${SERVER}:${BOT_PATH}/bot/utils/

# Перезагружаем бот
ssh root@89.58.17.123 "kill $(pgrep -f 'python main.py'); sleep 2; cd /opt/ramo_bot && /opt/ramo_bot/venv/bin/python main.py &"
```

## ⚠️ Открытые вопросы

- SSH ключ для git на сервере не настроен (использовали password-based auth для SCP)
- Нет systemd сервиса `ramo-bot.service` — бот запущен как фоновый процесс
- Рекомендация: настроить systemd сервис или supervisor для автозагрузки при перезагрузке сервера

## 📝 Команды для следующей сессии

```bash
# Проверить статус бота
ssh root@89.58.17.123 "ps aux | grep 'python main.py' | grep -v grep"

# Смотреть логи
ssh root@89.58.17.123 "tail -100 /opt/ramo_bot/bot.log" 2>/dev/null || echo "Логи не найдены"

# Общая информация о развёртывании
echo "Server: 89.58.17.123"
echo "Bot path: /opt/ramo_bot"
echo "Repo: git@gitlab.com:ramo_k-group1/ramo_bot.git"
echo "Branch deployed: dev"
echo "Latest commit: 9bcf9d3"
```

---

**Дата сессии:** 03.08.2026 13:57  
**Статус:** ✅ успешно развёрнут  
**Следующая сессия:** проверка логов, мониторинг работы, настройка systemd сервиса
