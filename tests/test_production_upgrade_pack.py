from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from viki.api.server import create_app
from viki.core.hive import HiveMind
from viki.core.repo_index import RepoIndex


class FailingProvider:
    def validate_config(self):
        return True

    def get_available_models(self):
        return ["fake/reasoning", "fake/coding"]

    async def complete(self, model, messages, **kwargs):
        system = messages[0]["content"].lower()
        if "planning swarm" in system:
            content = '''{
              "goal": "fix auth bug",
              "summary": "single task plan",
              "tasks": [
                {
                  "id": "task-1",
                  "title": "fix auth bug",
                  "objective": "fix auth bug in service",
                  "target_files": ["app/auth.py", "tests/test_auth.py"],
                  "deliverables": ["bugfix"],
                  "commands": [],
                  "skill_requests": []
                }
              ],
              "testing_commands": [],
              "acceptance_criteria": ["tests green"]
            }'''
        elif "coding swarm" in system:
            content = json.dumps(
                {
                    "task_id": "task-1",
                    "summary": "created tentative bugfix",
                    "file_operations": [
                        {"mode": "write", "path": "app/auth.py", "content": "value = 'candidate'\n"}
                    ],
                    "commands": [
                        {"command": "python -c \"import sys; print('fail'); sys.exit(1)\"", "timeout": 30}
                    ],
                    "skill_requests": [],
                    "notes": [],
                }
            )
        elif "debugging swarm" in system:
            content = '''{
              "summary": "repair still failing",
              "root_cause": "tests failing",
              "file_operations": [],
              "commands": [],
              "notes": []
            }'''
        elif "testing swarm" in system:
            content = '''{"summary": "skip", "commands": [], "expected_outputs": []}'''
        else:
            content = '''{"summary": "security ok", "issues": [], "recommended_commands": []}'''
        return {
            "content": content,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": model or "fake",
            "provider": "fake",
        }


def test_repo_index_prioritizes_relevant_files(tmp_path: Path):
    for index in range(260):
        (tmp_path / f"pkg/module_{index}.py").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f"pkg/module_{index}.py").write_text(f"def func_{index}():\n    return {index}\n", encoding="utf-8")
    (tmp_path / "services/auth_service.py").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "services/auth_service.py").write_text("class AuthService:\n    pass\n", encoding="utf-8")
    index = RepoIndex(tmp_path)
    profile = index.profile()
    focused = index.focus("fix auth service bug", limit=5)
    assert profile["large_repo"] is True
    assert focused[0]["path"] == "services/auth_service.py"


def test_failed_changes_stay_isolated_until_green(tmp_path: Path):
    (tmp_path / "app").mkdir(parents=True)
    (tmp_path / "app/auth.py").write_text("value = 'original'\n", encoding="utf-8")

    hive = HiveMind(FailingProvider(), tmp_path)

    async def run_case():
        await hive.initialize()
        try:
            return await hive.process_request("fix auth bug", mode="standard")
        finally:
            await hive.shutdown()

    result = asyncio.run(run_case())
    assert (tmp_path / "app/auth.py").read_text(encoding="utf-8") == "value = 'original'\n"
    assert result["task_results"][0]["sync"]["status"] == "kept_isolated_due_to_failures"
    assert "app/auth.py" in result["task_results"][0]["candidate_changed_files"]
    assert result["changed_files"] == []


def test_repo_profile_endpoint_and_command(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src/main.py").write_text("print('ok')\n", encoding="utf-8")
    app = create_app(tmp_path, provider=FailingProvider())
    client = TestClient(app)

    response = client.get("/repo/profile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["file_count"] >= 1

    server = app.state.viki_server
    reply = asyncio.run(server._handle_integration_command("/repo"))
    assert reply is not None
    assert "Repo files:" in reply
