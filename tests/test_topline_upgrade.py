from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from viki.api.server import create_app
from viki.core.repo_index import RepoIndex
from viki.core.worktree import WorktreeManager
from viki.infrastructure.database import DatabaseManager
from viki.ide.vscode import VSCodeIntegrator


class FakeProvider:
    def validate_config(self):
        return True

    def get_available_models(self):
        return ["fake/reasoning", "fake/coding"]

    async def complete(self, model, messages, **kwargs):
        system = messages[0]["content"].lower()
        if "planning swarm" in system:
            content = '''{
              "goal": "create a hello file",
              "summary": "single task plan",
              "tasks": [
                {
                  "id": "task-1",
                  "title": "write hello",
                  "objective": "write a hello.txt file",
                  "target_files": ["hello.txt"],
                  "deliverables": ["hello.txt"],
                  "commands": [],
                  "skill_requests": []
                }
              ],
              "testing_commands": [],
              "acceptance_criteria": ["hello.txt exists"]
            }'''
        elif "coding swarm" in system:
            content = '''{
              "task_id": "task-1",
              "summary": "created file",
              "file_operations": [
                {"mode": "write", "path": "hello.txt", "content": "hello from viki\\n"}
              ],
              "commands": [],
              "skill_requests": [],
              "notes": []
            }'''
        elif "testing swarm" in system:
            content = '{"summary": "no-op tests", "commands": [], "expected_outputs": []}'
        elif "debugging swarm" in system:
            content = '{"summary": "no repair needed", "root_cause": "none", "file_operations": [], "commands": [], "notes": []}'
        else:
            content = '{"summary": "security ok", "issues": [], "recommended_commands": []}'
        return {"content": content, "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, "model": model or "fake", "provider": "fake"}


def test_repo_index_instructions_dependencies_and_tests(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("Follow repo rules\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "feature.py").write_text("from pkg.core import alpha\n\ndef beta():\n    return alpha()\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_feature.py").write_text("from pkg.feature import beta\n", encoding="utf-8")

    index = RepoIndex(tmp_path)
    profile = index.profile()
    assert "AGENTS.md" in profile["instruction_files"]
    focused = index.focus("fix feature bug", target_files=["pkg/core.py"], limit=5)
    assert any(item["path"] == "pkg/feature.py" for item in focused)
    assert "tests/test_feature.py" in index.test_targets(["pkg/feature.py"])


def test_worktree_patch_bundle_exports_diff(tmp_path: Path):
    (tmp_path / ".viki-workspace").mkdir()
    (tmp_path / "hello.txt").write_text("before\n", encoding="utf-8")
    manager = WorktreeManager(tmp_path, tmp_path / ".viki-workspace" / "runs")
    worktree = manager.create("task-1")
    (worktree.root / "hello.txt").write_text("after\n", encoding="utf-8")
    preview = manager.diff_preview(worktree.root, ["hello.txt"])
    assert preview and preview[0]["added"] == 1
    patch_path = manager.export_patch_bundle(worktree.root, ["hello.txt"], tmp_path / ".viki-workspace" / "runs" / "task-1.patch")
    assert patch_path.exists()
    assert "+after" in patch_path.read_text(encoding="utf-8")
    manager.cleanup()


def test_api_run_diff_and_messaging_approval_command(tmp_path: Path):
    app = create_app(tmp_path, provider=FakeProvider())
    client = TestClient(app)

    response = client.post("/runs", json={"prompt": "create hello file"})
    assert response.status_code == 200
    session_id = response.json()["run"]["session_id"]

    diff_response = client.get(f"/runs/{session_id}/diff")
    assert diff_response.status_code == 200
    assert diff_response.json()["items"][0]["path"] == "hello.txt"

    db = DatabaseManager(str(tmp_path / ".viki-workspace" / "viki.db"))

    async def seed_approval():
        await db.initialize()
        return await db.create_approval(session_id, "command", "git push", "policy", 80, {"command": "git push"})

    approval_id = asyncio.run(seed_approval())
    class StubTelegramClient:
        def __init__(self):
            self.enabled = True
            self.secret = "secret"
            self.allowed_chat_ids = {"123"}
            self.messages = []

        def validate_secret(self, header_value):
            return header_value == self.secret

        def is_allowed_chat(self, chat_id):
            return chat_id in self.allowed_chat_ids

        def send_message(self, chat_id, text, reply_to_message_id=None):
            self.messages.append(text)
            return {"ok": True}

    server = app.state.viki_server
    server.telegram = StubTelegramClient()

    approve_response = client.post(
        "/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"message_id": 1, "text": f"/approve {approval_id}", "chat": {"id": 123}}},
    )
    assert approve_response.status_code == 200
    assert any("Approved" in item for item in server.telegram.messages)


def test_vscode_extension_scaffold_is_generated(tmp_path: Path):
    written = VSCodeIntegrator(tmp_path).install_extension_scaffold()
    assert (tmp_path / ".viki-workspace" / "ide" / "vscode-extension" / "package.json").exists()
    assert "extension.js" in written
