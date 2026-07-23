"""
Коннектор к внешней AI БД.
Graceful degradation: если AI БД недоступна — бот работает без рекомендаций.
"""
import logging
from typing import Any, Dict, List, Optional

from bot import config

logger = logging.getLogger(__name__)


class AIDbConnector:
    """Клиент для API внешней AI базы знаний."""

    def __init__(self):
        self.api_url = config.AI_DB_API_URL
        self.api_key = config.AI_DB_API_KEY
        self.available = bool(self.api_url and self.api_key)

    async def search_in_archive(
        self, query: str, index: str, filters: Optional[Dict] = None
    ) -> List[Dict]:
        """Поиск по индексированным архивам."""
        if not self.available:
            return []
        # TODO: реализовать HTTP-запрос к AI API
        logger.info(f"[AI DB] search: {query} in {index}")
        return []

    async def classify_incident(self, description: str) -> Dict[str, Any]:
        """Классифицирует инцидент по описанию."""
        if not self.available:
            return {"type": None, "confidence": 0.0}
        # TODO: реализовать
        logger.info(f"[AI DB] classify incident")
        return {"type": None, "confidence": 0.0}

    async def recommend_tags(self, handover_text: str) -> List[str]:
        """Рекомендует теги для передачи смены."""
        if not self.available:
            return []
        # TODO: реализовать
        logger.info(f"[AI DB] recommend tags")
        return []

    async def find_similar_incidents(
        self, incident_type: str, filters: Optional[Dict] = None
    ) -> List[Dict]:
        """Находит похожие прошлые инциденты."""
        if not self.available:
            return []
        # TODO: реализовать
        logger.info(f"[AI DB] find similar incidents")
        return []

    async def recommend_sop(self, problem_description: str) -> Optional[str]:
        """Рекомендует ID SOP-документа для проблемы."""
        if not self.available:
            return None
        # TODO: реализовать
        logger.info(f"[AI DB] recommend SOP")
        return None


# Singleton
_ai_connector: Optional[AIDbConnector] = None

def get_ai_connector() -> AIDbConnector:
    global _ai_connector
    if _ai_connector is None:
        _ai_connector = AIDbConnector()
    return _ai_connector
