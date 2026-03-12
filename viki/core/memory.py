from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..infrastructure.database import DatabaseManager


class MemoryBank:
    def __init__(self, db: DatabaseManager):
        self.db = db

    async def remember(self, session_id: str, kind: str, content: Dict[str, Any]) -> None:
        await self.db.store_memory(session_id, kind, content)

    async def recall(self, limit: int = 12) -> List[Dict[str, Any]]:
        return await self.db.get_memories(limit=limit)

    async def latest_checkpoint(self, session_id: str | None = None) -> Optional[Dict[str, Any]]:
        return await self.db.get_latest_checkpoint(session_id=session_id)
