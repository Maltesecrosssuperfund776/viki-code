from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .._aiosqlite import aiosqlite

from ..config import settings


class DatabaseManager:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.database_url.replace("sqlite:///", "")
        self._lock = asyncio.Lock()

    async def initialize(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    total_cost REAL DEFAULT 0.0,
                    total_tokens INTEGER DEFAULT 0,
                    git_branch TEXT,
                    user_request TEXT,
                    context_json TEXT,
                    result_json TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS swarms (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    parent_id TEXT,
                    type TEXT,
                    status TEXT,
                    depth INTEGER,
                    objective TEXT,
                    result_json TEXT,
                    cost_accumulated REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    checkpoint_type TEXT,
                    state_json TEXT,
                    git_commit_hash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    level TEXT,
                    agent_id TEXT,
                    action TEXT,
                    file_path TEXT,
                    details_json TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    command TEXT,
                    returncode INTEGER,
                    output TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    name TEXT,
                    description TEXT,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    request_type TEXT,
                    subject TEXT,
                    reason TEXT,
                    risk_score INTEGER,
                    payload_json TEXT,
                    status TEXT DEFAULT 'pending',
                    reviewer TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    kind TEXT,
                    content_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def create_session(self, session_id: str, user_request: str, git_branch: str, context: Dict[str, Any]) -> None:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO sessions (id, user_request, git_branch, context_json, status, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, user_request, git_branch, json.dumps(context), "active", datetime.now(timezone.utc).isoformat()),
                )
                await db.commit()

    async def update_session(self, session_id: str, status: str, result: Optional[Dict[str, Any]] = None) -> None:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE sessions SET status = ?, updated_at = ?, result_json = COALESCE(?, result_json) WHERE id = ?",
                    (status, datetime.now(timezone.utc).isoformat(), json.dumps(result) if result is not None else None, session_id),
                )
                await db.commit()

    async def update_session_cost(self, session_id: str, cost: float, tokens: int):
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE sessions SET total_cost = total_cost + ?, total_tokens = total_tokens + ?, updated_at = ? WHERE id = ?",
                    (cost, tokens, datetime.now(timezone.utc).isoformat(), session_id),
                )
                await db.commit()

    async def create_swarm(self, swarm_data: Dict[str, Any]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO swarms (id, session_id, parent_id, type, status, depth, objective, result_json, cost_accumulated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    swarm_data["id"],
                    swarm_data["session_id"],
                    swarm_data.get("parent_id"),
                    swarm_data["type"],
                    swarm_data["status"],
                    swarm_data["depth"],
                    swarm_data["objective"],
                    json.dumps(swarm_data.get("result_json")) if swarm_data.get("result_json") is not None else None,
                    swarm_data.get("cost_accumulated", 0.0),
                ),
            )
            await db.commit()

    async def update_swarm_status(self, swarm_id: str, status: str, result: Optional[Dict[str, Any]] = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE swarms SET status = ?, result_json = COALESCE(?, result_json) WHERE id = ?",
                (status, json.dumps(result) if result is not None else None, swarm_id),
            )
            await db.commit()

    async def create_checkpoint(self, session_id: str, state: Dict[str, Any], git_hash: str = ""):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO checkpoints (session_id, checkpoint_type, state_json, git_commit_hash) VALUES (?, ?, ?, ?)",
                (session_id, "auto", json.dumps(state), git_hash),
            )
            await db.execute(
                "DELETE FROM checkpoints WHERE id NOT IN (SELECT id FROM checkpoints WHERE session_id = ? ORDER BY id DESC LIMIT 20)",
                (session_id,),
            )
            await db.commit()

    async def get_latest_checkpoint(self, session_id: str | None = None) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM checkpoints"
        params: tuple[Any, ...] = ()
        if session_id:
            query += " WHERE session_id = ?"
            params = (session_id,)
        query += " ORDER BY id DESC LIMIT 1"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def audit_log(self, level: str, agent_id: str, action: str, file_path: str | None = None, details: Optional[Dict[str, Any]] = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO audit_log (level, agent_id, action, file_path, details_json) VALUES (?, ?, ?, ?, ?)",
                (level, agent_id, action, file_path, json.dumps(details) if details is not None else None),
            )
            await db.commit()

    async def record_command(self, session_id: str, command: str, result: Dict[str, Any]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO commands (session_id, command, returncode, output, error) VALUES (?, ?, ?, ?, ?)",
                (session_id, command, result.get("returncode"), result.get("output", ""), result.get("error", "")),
            )
            await db.commit()

    async def recent_command_failures(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM commands WHERE returncode IS NOT NULL AND returncode != 0 ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def record_skill(self, session_id: str, name: str, description: str, source: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO skills (session_id, name, description, source) VALUES (?, ?, ?, ?)",
                (session_id, name, description, source),
            )
            await db.commit()

    async def create_approval(self, session_id: str, request_type: str, subject: str, reason: str, risk_score: int, payload: Dict[str, Any]) -> int:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "INSERT INTO approvals (session_id, request_type, subject, reason, risk_score, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, request_type, subject, reason, risk_score, json.dumps(payload)),
                )
                await db.commit()
                return int(cursor.lastrowid)


    async def get_approval(self, approval_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def resolve_approval(self, approval_id: int, status: str, reviewer: str) -> None:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE approvals SET status = ?, reviewer = ?, resolved_at = ? WHERE id = ?",
                    (status, reviewer, datetime.now(timezone.utc).isoformat(), approval_id),
                )
                await db.commit()

    async def list_approvals(self, status: str = "pending", limit: int = 50) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def store_memory(self, session_id: str, kind: str, content: Dict[str, Any]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO memories (session_id, kind, content_json) VALUES (?, ?, ?)",
                (session_id, kind, json.dumps(content)),
            )
            await db.commit()

    async def get_memories(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM memories ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_latest_session(self) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1")
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
