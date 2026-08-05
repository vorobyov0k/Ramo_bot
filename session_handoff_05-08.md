---
date: 2026-08-05
tag: BOT_RECOVERY_COMPLETE
status: ✅ успешно восстановлен и проверен
session_id: "#DEV TG-RAMOBOT3"
---

# Сессия 05-08 — Восстановление RAMO-бота (systemd deployment)

## Диагностика проблемы

**Проблема:** Бот перестал отвечать после подготовки systemd-сервиса в сессии 04-08.

**Причина:** Systemd-сервис (`ramo-bot.service`) был создан локально, но **никогда не был скопирован на сервер**. Файл `C:\Users\user\Desktop\AMO\ramo-bot.service` остался только на локальной машине.

**Результат:** Процесс бота был полностью выключен (не было ни ручного запуска, ни systemd-управления).

## ✅ Что было сделано

### 1. Диагностика на сервере
```
ps aux | grep "main.py" | grep -v grep  → нет процессов
systemctl status ramo-bot.service        → Unit not found
journalctl -u ramo-bot.service           → No entries
```

### 2. Создание и деплой systemd-сервиса

**Проблема с heredoc в PowerShell/PuTTY:** Multi-line команды с `<< 'EOF'` не вставлялись корректно из-за особенностей терминала.

**Решение:** Создание файла на локальной Windows-машине, затем SCP-копирование на сервер.

**Процесс:**
1. Создал файл `C:\ramo-bot.service` в PowerShell (локально)
2. Скопировал на сервер: `scp C:\ramo-bot.service root@89.58.17.123:/tmp/`
3. На сервере: `sudo cp /tmp/ramo-bot.service /etc/systemd/system/`
4. Перезагрузил systemd: `sudo systemctl daemon-reload`
5. Включил автозагрузку: `sudo systemctl enable ramo-bot.service`
6. Запустил: `sudo systemctl start ramo-bot.service`

### 3. Проверка статуса
```
● ramo-bot.service - RAMO Telegram Bot Service
     Loaded: loaded (/etc/systemd/system/ramo-bot.service; enabled; preset: enabled)
     Active: active (running) since Wed 2026-08-05 12:29:08 CEST
   Main PID: 115528 (python)
      Tasks: 5 (limit: 4636)
     Memory: 105.7M (peak: 107.7M)
```

✅ Бот запущен, отвечает в Telegram на `/start`

## 📋 Итоговое состояние (05.08.2026 12:30)

**Сервер:** `89.58.17.123:/opt/ramo_bot`
**Systemd сервис:** `/etc/systemd/system/ramo-bot.service` ✅ active
**Процесс:** PID 115528 ✅
**Автозагрузка:** ✅ enabled
**Telegram:** ✅ отвечает

## 🚀 Команды для мониторинга/управления

```bash
# Статус
sudo systemctl status ramo-bot.service --no-pager

# Логи real-time
sudo journalctl -u ramo-bot.service -f

# Перезагрузка
sudo systemctl restart ramo-bot.service

# Остановка
sudo systemctl stop ramo-bot.service

# Запуск
sudo systemctl start ramo-bot.service
```

## ⚠️ Важно: что изменилось

**ЕДИНСТВЕННЫЙ способ управления ботом — через systemd:**
```bash
sudo systemctl {start|stop|restart|status} ramo-bot.service
```

**Ручной запуск `python main.py &` больше НЕ ИСПОЛЬЗОВАТЬ** — это вызовет конфликт двух процессов и 409 Conflict от Telegram.

## 📝 Файлы в проекте

- `C:\Users\user\Desktop\AMO\ramo-bot.service` — systemd unit (уже на сервере в `/etc/systemd/system/`)
- `C:\Users\user\Desktop\AMO\deploy-systemd.ps1` — скрипт для будущих деплоев (рекомендация: добавить `sudo pkill -f "main.py"` перед стартом, чтобы избежать конфликтов)

## 🔄 Следующие сессии

Если нужно обновить код бота:
1. `git pull origin dev` (локально в AMO-dev)
2. `scp bot/handlers/*.py root@89.58.17.123:/opt/ramo_bot/bot/handlers/` (и прочие изменённые файлы)
3. `ssh root@89.58.17.123 "sudo systemctl restart ramo-bot.service"`

Или использовать `deploy-systemd.ps1` с добавлением `sudo pkill -f "main.py"` перед стартом.

---

**Дата сессии:** 05.08.2026 12:30  
**Статус:** ✅ Бот восстановлен и работает  
**Следующая сессия:** мониторинг, профилактика, настройка SSH-ключа (опционально)
