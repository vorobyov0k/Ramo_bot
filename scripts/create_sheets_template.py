#!/usr/bin/env python3
"""
Скрипт создания Google Sheets таблицы со всеми листами для RAMO-бота.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from bot import config
from bot.utils.google_sheets_api import get_sheets_connector

SHEETS = [
    "bot_users", "shifts_schedule", "events_calendar", "sop_documents",
    "job_instructions", "wine_menu", "food_menu", "hall_map",
    "contacts_directory", "faq_base", "department_hierarchy",
    "access_control", "manager_task_templates",
]

HEADERS = {
    "bot_users": ["telegram_id", "full_name", "role", "requested_role", "department",
                  "phone", "hire_date", "mentor_id", "active", "status", "timezone"],
    "shifts_schedule": ["shift_id", "date", "department", "user_id", "start_time", "end_time", "position"],
    "events_calendar": ["event_id", "title", "date", "time", "event_type", "description", "related_roles", "image_url"],
    "sop_documents": ["doc_id", "title", "category", "content", "version", "updated_date", "related_roles"],
    "job_instructions": ["position", "responsibilities", "daily_tasks", "opening_checklist",
                         "closing_checklist", "shift_duties_checklists", "version"],
    "wine_menu": ["wine_id", "name", "type", "country", "year", "description", "price", "pairing"],
    "food_menu": ["dish_id", "name", "category", "description", "price", "ingredients", "allergens"],
    "hall_map": ["zone_id", "zone_name", "responsible_positions", "tables", "description"],
    "contacts_directory": ["contact_id", "name", "phone", "email", "category"],
    "faq_base": ["faq_id", "question", "answer", "category", "for_guests"],
    "department_hierarchy": ["dept_id", "dept_name", "parent_dept_id", "manager_id", "members", "can_view_handovers"],
    "access_control": ["access_id", "user_id", "resource_type", "resource_filter", "permission", "created_at"],
    "manager_task_templates": ["template_id", "title", "description", "priority", "default_deadline_hours", "created_by"],
}


def create_spreadsheet(service, title="RAMO Bot Data"):
    spreadsheet = {
        "properties": {"title": title},
        "sheets": [{"properties": {"title": name}} for name in SHEETS],
    }
    try:
        result = service.spreadsheets().create(body=spreadsheet).execute()
        return result["spreadsheetId"], result["spreadsheetUrl"]
    except HttpError as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)


def add_headers(service, spreadsheet_id):
    for sheet_name, headers in HEADERS.items():
        body = {"values": [headers]}
        try:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                body=body,
            ).execute()
            print(f"  ✅ {sheet_name}")
        except HttpError as e:
            print(f"  ⚠️ {sheet_name}: {e}")


def update_env(spreadsheet_id):
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    content = env_path.read_text(encoding="utf-8")
    if "GOOGLE_SHEETS_SPREADSHEET_ID=" in content:
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            if line.startswith("GOOGLE_SHEETS_SPREADSHEET_ID="):
                new_lines.append(f"GOOGLE_SHEETS_SPREADSHEET_ID={spreadsheet_id}")
            else:
                new_lines.append(line)
        content = "\n".join(new_lines)
    else:
        content += f"\nGOOGLE_SHEETS_SPREADSHEET_ID={spreadsheet_id}\n"
    env_path.write_text(content, encoding="utf-8")
    print("✅ .env обновлён")


def main():
    print("🚀 Создание Google Sheets для RAMO...\n")
    if not config.GOOGLE_TOKEN_FILE.exists():
        print("❌ Сначала запусти: python scripts/get_google_token.py")
        sys.exit(1)

    service = build("sheets", "v4", credentials=get_sheets_connector().creds)
    print("📊 Создаю таблицу...")
    spreadsheet_id, url = create_spreadsheet(service)

    print(f"\n✅ Таблица создана!")
    print(f"   ID: {spreadsheet_id}")
    print(f"   URL: {url}")

    print(f"\n📝 Добавляю заголовки...")
    add_headers(service, spreadsheet_id)

    print(f"\n💾 Обновляю .env...")
    update_env(spreadsheet_id)

    print(f"\n{'='*60}")
    print("📋 ДАЛЬШЕ:")
    print(f"1. Открой: {url}")
    print("2. Заполни лист bot_users (начни с себя)")
    print("3. Запускай бота: python -m bot.main")
    print('='*60)


if __name__ == "__main__":
    main()