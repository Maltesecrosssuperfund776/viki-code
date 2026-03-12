from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Log, Static

from ..infrastructure.database import DatabaseManager


class DashboardApp(App):
    CSS = """
    Screen { layout: vertical; }
    #top { height: 1fr; }
    #sessions, #approvals { width: 1fr; }
    #logs { height: 12; }
    """

    def __init__(self, db_path: str | Path):
        super().__init__()
        self.db = DatabaseManager(str(db_path))

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("VIKI Operations Dashboard", id="title")
        with Horizontal(id="top"):
            with Vertical(id="sessions"):
                yield Static("Recent Sessions")
                yield DataTable(id="sessions_table")
            with Vertical(id="approvals"):
                yield Static("Pending Approvals")
                yield DataTable(id="approvals_table")
        yield Log(id="logs")
        yield Footer()

    async def on_mount(self) -> None:
        await self.db.initialize()
        sessions_table = self.query_one("#sessions_table", DataTable)
        sessions_table.add_columns("Session", "Status", "Request")
        approvals_table = self.query_one("#approvals_table", DataTable)
        approvals_table.add_columns("ID", "Type", "Risk", "Subject")
        self.set_interval(2.0, self.refresh_data)
        await self.refresh_data()

    async def refresh_data(self) -> None:
        sessions = await self.db.get_recent_sessions(20)
        approvals = await self.db.list_approvals(status="pending", limit=20)
        sessions_table = self.query_one("#sessions_table", DataTable)
        approvals_table = self.query_one("#approvals_table", DataTable)
        sessions_table.clear(columns=False)
        approvals_table.clear(columns=False)
        for item in sessions:
            sessions_table.add_row(item["id"], item.get("status", "?"), (item.get("user_request") or "")[:80])
        for item in approvals:
            approvals_table.add_row(str(item["id"]), item.get("request_type", "?"), str(item.get("risk_score", 0)), item.get("subject", ""))
        logs = self.query_one("#logs", Log)
        logs.clear()
        for item in sessions[:8]:
            logs.write_line(json.dumps({"session": item["id"], "status": item.get("status")}, ensure_ascii=False))


class VikiDashboard:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def start(self):
        DashboardApp(self.db_path).run()


def launch_dashboard(db_path: str | Path):
    DashboardApp(db_path).run()
