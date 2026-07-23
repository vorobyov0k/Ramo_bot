#!/usr/bin/env python3
"""
Загрузка файла(ов) в отдельную папку Google Drive.

Использует OAuth 2.0 с МИНИМАЛЬНЫМ правом `drive.file` — скрипт видит и
трогает только те файлы/папки, которые создал сам. Полный Drive ему недоступен.
Токен кэшируется в token_drive.json (отдельно от token.json бота; в .gitignore).

Запуск:
    python scripts/upload_to_drive.py <путь_к_файлу> [имя_папки]

Пример:
    python scripts/upload_to_drive.py RAMO_bot.zip "RAMO_bot_backup"
"""
import sys
from pathlib import Path

# Консоль Windows (cp1251) не печатает эмодзи → форсируем UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN = ROOT / "token_drive.json"


def get_creds():
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Обновляю токен...")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                print(f"❌ Нет {CLIENT_SECRET.name} в корне проекта")
                sys.exit(1)
            print("🌐 Открываю браузер для согласия Google (право: drive.file)...")
            print("   Войди в Google-аккаунт RAMO и нажми «Разрешить».\n")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
        print(f"✅ Токен сохранён: {TOKEN.name}")
    return creds


def ensure_folder(service, name, parent=None):
    """Находит папку (созданную этим приложением) или создаёт новую."""
    q = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{name}' and trashed=false"
    )
    if parent:
        q += f" and '{parent}' in parents"
    res = service.files().list(
        q=q, spaces="drive", fields="files(id,name)"
    ).execute()
    found = res.get("files", [])
    if found:
        print(f"📁 Папка уже есть: {name} ({found[0]['id']})")
        return found[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent:
        meta["parents"] = [parent]
    folder = service.files().create(body=meta, fields="id,webViewLink").execute()
    print(f"📁 Создана папка: {name} ({folder['id']})")
    print(f"   Ссылка: {folder.get('webViewLink', '—')}")
    return folder["id"]


def upload(service, filepath: Path, folder_id: str):
    if not filepath.exists():
        print(f"❌ Файл не найден: {filepath}")
        sys.exit(1)
    media = MediaFileUpload(str(filepath), resumable=True)
    meta = {"name": filepath.name, "parents": [folder_id]}
    print(f"⬆️  Загружаю {filepath.name} ({filepath.stat().st_size:,} байт)...")
    f = service.files().create(
        body=meta, media_body=media,
        fields="id,name,webViewLink,size",
    ).execute()
    print(f"✅ Загружено: {f['name']}")
    print(f"   Открыть: {f.get('webViewLink', '—')}")
    return f


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    filepath = Path(sys.argv[1]).expanduser().resolve()
    folder_name = sys.argv[2] if len(sys.argv) > 2 else "RAMO_bot_backup"

    creds = get_creds()
    service = build("drive", "v3", credentials=creds)
    folder_id = ensure_folder(service, folder_name)
    upload(service, filepath, folder_id)
    print("\n🎉 Готово.")


if __name__ == "__main__":
    main()
