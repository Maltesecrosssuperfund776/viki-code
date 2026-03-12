from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Optional

try:
    import aiosqlite as _aiosqlite  # type: ignore
except Exception:
    _aiosqlite = None


if _aiosqlite is not None:
    aiosqlite = _aiosqlite
else:
    class Row(sqlite3.Row):
        pass

    class Cursor:
        def __init__(self, cursor: sqlite3.Cursor):
            self._cursor = cursor

        @property
        def lastrowid(self):
            return self._cursor.lastrowid

        async def fetchone(self):
            return self._cursor.fetchone()

        async def fetchall(self):
            return self._cursor.fetchall()

    class Connection:
        def __init__(self, path: str):
            self._conn = sqlite3.connect(path)
            self.row_factory = None

        async def __aenter__(self):
            if self.row_factory is not None:
                self._conn.row_factory = self.row_factory
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._conn.close()

        async def execute(self, sql: str, params: Iterable[Any] = ()):
            if self.row_factory is not None:
                self._conn.row_factory = self.row_factory
            cur = self._conn.execute(sql, tuple(params))
            return Cursor(cur)

        async def commit(self):
            self._conn.commit()

    class _Module:
        Row = sqlite3.Row

        @staticmethod
        def connect(path: str):
            return Connection(path)

    aiosqlite = _Module()
