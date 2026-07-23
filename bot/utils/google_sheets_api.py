"""
Коннектор к Google Sheets API.
Использует OAuth 2.0 (token.json) для авторизации.
"""
from typing import Any, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from bot import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

class GoogleSheetsConnector:
    """Класс для работы с Google Sheets API."""

    def __init__(self):
        self.service = None
        self.creds = None
        self._connect()

    def _connect(self):
        """Устанавливает соединение с Google Sheets API."""
        token_path = config.GOOGLE_TOKEN_FILE
        client_secret_path = config.GOOGLE_CLIENT_SECRET_FILE

        if not token_path.exists():
            raise FileNotFoundError(
                f"token.json не найден: {token_path}\n"
                f"Запусти: python scripts/get_google_token.py"
            )

        self.creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if self.creds.expired and self.creds.refresh_token:
            self.creds.refresh(Request())
            # Сохраняем обновлённый токен
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(self.creds.to_json())

        self.service = build("sheets", "v4", credentials=self.creds)

    def get_sheet_data(self, range_name: str) -> List[List[Any]]:
        """
        Читает данные из указанного диапазона таблицы.

        Args:
            range_name: Например "bot_users!A1:Z1000"

        Returns:
            Список строк (списков значений)
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=config.GOOGLE_SHEETS_SPREADSHEET_ID, range=range_name)
                .execute()
            )
            return result.get("values", [])
        except HttpError as e:
            raise RuntimeError(f"Ошибка чтения Google Sheets: {e}")

    def update_sheet_data(self, range_name: str, values: List[List[Any]]) -> dict:
        """
        Записывает данные в указанный диапазон таблицы.

        Args:
            range_name: Например "bot_users!A2"
            values: Список строк для записи
        """
        body = {"values": values}
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=config.GOOGLE_SHEETS_SPREADSHEET_ID,
                    range=range_name,
                    valueInputOption="RAW",
                    body=body,
                )
                .execute()
            )
            return result
        except HttpError as e:
            raise RuntimeError(f"Ошибка записи в Google Sheets: {e}")

    def get_spreadsheet_info(self) -> dict:
        """Возвращает информацию о таблице (название, листы)."""
        try:
            return (
                self.service.spreadsheets()
                .get(spreadsheetId=config.GOOGLE_SHEETS_SPREADSHEET_ID)
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"Ошибка получения информации о таблице: {e}")

# Глобальный инстанс (singleton)
_sheets_connector: Optional[GoogleSheetsConnector] = None

def get_sheets_connector() -> GoogleSheetsConnector:
    """Возвращает singleton-инстанс коннектора."""
    global _sheets_connector
    if _sheets_connector is None:
        _sheets_connector = GoogleSheetsConnector()
    return _sheets_connector
