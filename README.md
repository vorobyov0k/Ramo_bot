# 🤖 RAMO Telegram Bot

Корпоративный Telegram-бот для ресторана RAMO. База знаний, чек-листы, передача смен, инциденты, онбординг.

## Стек

- **Python 3.10+**
- **aiogram 3.x** — Telegram Bot API
- **SQLAlchemy + aiosqlite** — локальная БД
- **Google Sheets API** — источник истины для справочников
- **JSON-кэш** — быстрый доступ к данным

## Быстрый старт

### 1. Установка зависимостей

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Настройка окружения

```bash
cp .env.example .env
# Отредактируй .env — вставь BOT_TOKEN и ADMIN_TELEGRAM_ID
```

### 3. Google OAuth авторизация

Положи `client_secret.json` (скачанный из Google Cloud Console) в корень проекта.

```bash
python scripts/get_google_token.py
```

Откроется браузер — залогинься в Google-аккаунт RAMO и дай доступ. `token.json` создастся автоматически.

### 4. Запуск бота

```bash
python -m bot.main
```

## Структура проекта

```
ramo-telegram-bot/
├── bot/
│   ├── main.py                 # Точка входа
│   ├── handlers/               # Обработчики команд и кнопок
│   ├── middlewares/            # Auth, логирование
│   ├── keyboards/              # Inline-кнопки
│   ├── states/                 # FSM (Finite State Machine)
│   └── utils/                  # Коннекторы (БД, Google Sheets, AI, кэш)
├── data/
│   ├── cache/                  # JSON-кэши
│   └── archive/                # Архивные данные
├── scripts/
│   └── get_google_token.py     # Первичная OAuth-авторизация
├── config.py                   # Конфигурация
├── requirements.txt
└── .env                        # Переменные окружения (не коммитить!)
```

## Роли пользователей

| Роль | Доступ |
|------|--------|
| `admin` | Полный доступ |
| `manager` | Контроль команды, инциденты, рассылка |
| `barman` | Чек-листы, handover, инциденты, библиотека |
| `waiter` | Чек-листы, handover, инциденты, библиотека |
| `security` | Чек-листы, handover, инциденты, библиотека |
| `newcomer` | Онбординг, библиотека |

## Регистрация

1. Пользователь нажимает `/start`
2. Вводит ФИО и выбирает должность
3. Заявка отправляется администратору на одобрение
4. Админ получает уведомление: «Одобрить / Отклонить»
5. После одобрения — доступ к полному функционалу

## Разработка

### Добавить новый handler

1. Создай файл в `bot/handlers/`
2. Импортируй роутер в `bot/main.py`
3. Подключи через `dp.include_router()`

### Работа с БД

```python
from bot.utils.db_connector import get_user_by_telegram_id, create_pending_user

user = await get_user_by_telegram_id(123456789)
```

### Работа с Google Sheets

```python
from bot.utils.google_sheets_api import get_sheets_connector

sheets = get_sheets_connector()
data = sheets.get_sheet_data("bot_users!A1:Z100")
```

## Лицензия

Внутренний проект RAMO.
