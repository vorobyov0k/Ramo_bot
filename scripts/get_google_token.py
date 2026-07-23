#!/usr/bin/env python3
"""
Скрипт первичной авторизации Google OAuth 2.0.
Запускается ОДИН РАЗ для получения token.json.

Инструкция:
1. Положи client_secret.json в корень проекта (рядом со скриптом)
2. Запусти: python scripts/get_google_token.py
3. В браузере выбери Google-аккаунт RAMO и дай доступ
4. token.json сохранится автоматически
"""
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from bot import config

# Scopes для чтения и записи Google Sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

def main():
    creds = None
    token_path = config.GOOGLE_TOKEN_FILE
    client_secret_path = config.GOOGLE_CLIENT_SECRET_FILE

    # Проверяем наличие client_secret.json
    if not client_secret_path.exists():
        print(f"❌ Файл не найден: {client_secret_path}")
        print("Положи client_secret.json в корень проекта")
        sys.exit(1)

    # Если token.json уже есть — обновляем
    if token_path.exists():
        print(f"🔄 Найден существующий {token_path}, обновляем...")
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Если нет валидных creds — запускаем OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Токен истёк, обновляем...")
            creds.refresh(Request())
        else:
            print("🌐 Открываю браузер для авторизации...")
            print("Выбери Google-аккаунт RAMO и дай доступ\n")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Сохраняем token.json
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
        print(f"✅ Токен сохранён: {token_path}")
    else:
        print(f"✅ Токен валиден: {token_path}")

    # Тестовый вызов — проверяем доступ к Sheets API
    print("\n🧪 Проверяю доступ к Google Sheets API...")
    from googleapiclient.discovery import build
    service = build("sheets", "v4", credentials=creds)

    # Пробуем получить информацию о таблице
    if config.GOOGLE_SHEETS_SPREADSHEET_ID:
        try:
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=config.GOOGLE_SHEETS_SPREADSHEET_ID
            ).execute()
            print(f"✅ Доступ есть! Таблица: {spreadsheet['properties']['title']}")
        except Exception as e:
            print(f"⚠️ Токен работает, но не удалось открыть таблицу: {e}")
            print("Проверь GOOGLE_SHEETS_SPREADSHEET_ID в .env")
    else:
        print("⚠️ GOOGLE_SHEETS_SPREADSHEET_ID не задан в .env")
        print("Токен получен, но тест таблицы пропущен")

if __name__ == "__main__":
    main()
