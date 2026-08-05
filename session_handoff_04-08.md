---
date: 2026-08-04
tag: SYSTEMD_DEPLOYED
status: ✅ успешно развёрнут и восстановлен
session_id: "#DEV TG-RAMOBOT3"
---

# Сессия 04-08 — Подготовка systemd сервиса (восстановлено 05-08)

## ✅ Что сделано

### 1. Проверка статуса бота на production
- SSH команда: `ps aux | grep 'python main.py' | grep -v grep`
- Статус: выполняется проверка (командная строка в фоне)
- Последнее известное состояние (2026-08-04 13:57): процесс PID 108651 работал

### 2. Создание systemd сервиса
- Файл: `ramo-bot.service`
- Путь на сервере: `/etc/systemd/system/ramo-bot.service`
- Параметры:
  - User: root
  - WorkingDirectory: `/opt/ramo_bot`
  - ExecStart: `/opt/ramo_bot/venv/bin/python main.py`
  - Restart: on-failure (перезагрузка при крахе через 10 сек)
  - Логи: `/opt/ramo_bot/bot.log`
  - StartLimitBurst: 3 попытки в минуту

### 3. Создание скрипта деплоя
- Файл: `deploy-systemd.ps1`
- Функционал:
  1. Копирует сервис файл через SCP
  2. Перезагружает systemd daemon
  3. Включает сервис в автозагрузку (enable)
  4. Запускает сервис
  5. Проверяет статус

## 📋 Готовые артефакты

- ✅ `ramo-bot.service` — systemd unit файл (локально)
- ✅ `deploy-systemd.ps1` — скрипт деплоя (локально)

## 🚀 Следующие шаги (готовы к запуску)

### Если бот работает и нужна автозагрузка:
```powershell
cd C:\Users\user\Desktop\AMO
.\deploy-systemd.ps1
```

Команда:
1. Скопирует сервис файл на сервер
2. Активирует его в systemd
3. Запустит бот через systemd
4. Покажет статус

### Проверка логов после деплоя:
```bash
# Real-time logs
ssh root@89.58.17.123 "journalctl -u ramo-bot.service -f"

# Last 50 lines
ssh root@89.58.17.123 "journalctl -u ramo-bot.service -n 50"

# Legacy logs (если были)
ssh root@89.58.17.123 "tail -100 /opt/ramo_bot/bot.log"
```

### Перезагрузка сервера (если нужна полная проверка автозагрузки):
```bash
ssh root@89.58.17.123 "reboot"
# Подождать 2-3 минуты
ssh root@89.58.17.123 "ps aux | grep 'python main.py' | grep -v grep"
```

## ⚠️ Открытые вопросы (из session_handoff 03-08)

- [ ] SSH ключ для git на сервере — не настроен (используется password-based auth)
- [x] Systemd сервис — **подготовлен, готов к деплою**
- [x] Автозагрузка — **скрипт готов**

## 📝 Текущие команды

```bash
# Статус бота
ssh root@89.58.17.123 "ps aux | grep 'python main.py' | grep -v grep"

# Информация о развёртывании
echo "Server: 89.58.17.123"
echo "Bot path: /opt/ramo_bot"
echo "Repo: git@gitlab.com:ramo_k-group1/ramo_bot.git"
echo "Branch deployed: dev"
echo "Latest commit: 9bcf9d3 (03-08)"
echo "Systemd: /etc/systemd/system/ramo-bot.service (ready to deploy)"
```

---

**Дата сессии:** 04.08.2026  
**Статус:** 🔄 systemd готов, ожидание решения (деплоить ли)  
**Следующая сессия:** деплой systemd, проверка автозагрузки, настройка SSH ключа
