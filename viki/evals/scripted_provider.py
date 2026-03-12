from __future__ import annotations

import json
import re
from typing import Any, Dict, List


class ScriptedEvalProvider:
    """Deterministic offline provider for benchmark and smoke harnesses."""

    def validate_config(self) -> bool:
        return True

    def get_available_models(self) -> List[str]:
        return ["scripted/reasoning", "scripted/coding", "scripted/fast"]

    async def complete(self, model: str | None, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        system = messages[0]["content"].lower()
        joined = "\n".join(str(item.get("content", "")) for item in messages)
        if "planning swarm" in system:
            content = json.dumps(self._plan(joined))
        elif "coding swarm" in system:
            content = json.dumps(self._code(joined))
        elif "debugging swarm" in system:
            content = json.dumps(self._debug(joined))
        elif "testing swarm" in system:
            content = json.dumps(self._test(joined))
        else:
            content = json.dumps({"summary": "security ok", "issues": [], "recommended_commands": []})
        return {
            "content": content,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": model or "scripted",
            "provider": "scripted",
        }

    def _detect_filename(self, text: str) -> str:
        match = re.search(r"(?:create|write|add)\s+([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)", text, flags=re.I)
        if match:
            return match.group(1)
        if "multiply bug" in text.lower():
            return "app/calculator.py"
        if "broken feature" in text.lower():
            return "pkg/feature_4.py"
        if "account normalization" in text.lower() or "old helper" in text.lower():
            return "packages/shared/auth.py"
        if "normalize_account" in text.lower() or "normalize_user" in text:
            return "apps/api/service.py"
        if "legacy_sum" in text.lower() or "sum_numbers" in text.lower():
            return "consumer.py"
        if "change_runbook" in text.lower() or "commands to validate" in text.lower():
            return "CHANGE_RUNBOOK.md"
        if "repo_overview" in text.lower() or "repo overview" in text.lower():
            return "REPO_OVERVIEW.md"
        return "hello.txt"

    def _plan(self, text: str) -> Dict[str, Any]:
        filename = self._detect_filename(text)
        target_files = [filename]
        if "multiply bug" in text.lower():
            target_files.append("tests/test_calculator.py")
        if "broken feature" in text.lower():
            target_files.append("tests/test_feature_4.py")
        if "account normalization" in text.lower() or "old helper" in text.lower():
            target_files.extend(["apps/api/service.py", "apps/cli/commands.py", "docs/auth.md", "tests/test_service.py", "tests/test_cli.py"])
        elif "normalize_account" in text.lower() or "normalize_user" in text:
            target_files.extend(["packages/shared/auth.py", "tests/test_service.py"])
        if "legacy_sum" in text.lower() or "sum_numbers" in text.lower():
            target_files.append("tests/test_consumer.py")
        return {
            "goal": filename,
            "summary": "scripted benchmark plan",
            "tasks": [
                {
                    "id": "task-1",
                    "title": f"work on {filename}",
                    "objective": f"update {filename}",
                    "target_files": target_files,
                    "deliverables": target_files,
                    "commands": [],
                    "skill_requests": [],
                }
            ],
            "testing_commands": [],
            "acceptance_criteria": [f"{filename} updated"],
        }

    def _code(self, text: str) -> Dict[str, Any]:
        lowered = text.lower()
        if "multiply bug" in lowered:
            return {
                "task_id": "task-1",
                "summary": "fix multiply implementation",
                "file_operations": [
                    {"mode": "write", "path": "app/calculator.py", "content": "def multiply(a: int, b: int) -> int:\n    return a * b\n"}
                ],
                "commands": [{"command": "pytest -q tests/test_calculator.py", "timeout": 120}],
                "skill_requests": [],
                "notes": ["scripted bug fix"],
            }
        if "broken feature" in lowered:
            return {
                "task_id": "task-1",
                "summary": "fix feature_4 implementation",
                "file_operations": [
                    {"mode": "write", "path": "pkg/feature_4.py", "content": "def feature_4(value):\n    return value + 4\n"}
                ],
                "commands": [{"command": "pytest -q tests/test_feature_4.py", "timeout": 120}],
                "skill_requests": [],
                "notes": ["scripted matrix repair"],
            }
        if "account normalization" in lowered or "old helper" in lowered:
            return {
                "task_id": "task-1",
                "summary": "roll out normalize_account across the monorepo",
                "file_operations": [
                    {
                        "mode": "write",
                        "path": "packages/shared/auth.py",
                        "content": "def normalize_user(name: str) -> str:\n    return name.strip().lower()\n\n\ndef normalize_account(name: str) -> str:\n    return normalize_user(name)\n",
                    },
                    {
                        "mode": "write",
                        "path": "apps/api/service.py",
                        "content": "from packages.shared.auth import normalize_account\n\n\ndef handler(name: str) -> str:\n    return normalize_account(name)\n",
                    },
                    {
                        "mode": "write",
                        "path": "apps/cli/commands.py",
                        "content": "from packages.shared.auth import normalize_account\n\n\ndef normalize_input(name: str) -> str:\n    return normalize_account(name)\n",
                    },
                    {
                        "mode": "write",
                        "path": "docs/auth.md",
                        "content": "# Auth naming\n\nUse `normalize_account` for new call sites. `normalize_user` remains as the compatibility shim.\n",
                    }
                ],
                "commands": [{"command": "pytest -q tests/test_service.py tests/test_cli.py", "timeout": 120}],
                "skill_requests": [],
                "notes": ["scripted monorepo rollout"],
            }
        if "normalize_account" in lowered or "normalize_user" in lowered:
            return {
                "task_id": "task-1",
                "summary": "refactor normalize_user flow",
                "file_operations": [
                    {
                        "mode": "write",
                        "path": "packages/shared/auth.py",
                        "content": "def normalize_user(name: str) -> str:\n    return name.strip().lower()\n\n\ndef normalize_account(name: str) -> str:\n    return normalize_user(name)\n",
                    },
                    {
                        "mode": "write",
                        "path": "apps/api/service.py",
                        "content": "from packages.shared.auth import normalize_account\n\n\ndef handler(name: str) -> str:\n    value = normalize_account(name)\n    return value\n",
                    }
                ],
                "commands": [{"command": "pytest -q tests/test_service.py", "timeout": 120}],
                "skill_requests": [],
                "notes": ["scripted refactor"],
            }
        if "legacy_sum" in lowered or "sum_numbers" in lowered:
            return {
                "task_id": "task-1",
                "summary": "migrate consumer to new api",
                "file_operations": [
                    {
                        "mode": "write",
                        "path": "consumer.py",
                        "content": "from new_api import sum_numbers\n\n\ndef total(values):\n    return sum_numbers(values)\n",
                    }
                ],
                "commands": [{"command": "pytest -q tests/test_consumer.py", "timeout": 120}],
                "skill_requests": [],
                "notes": ["scripted migration"],
            }
        if "repo_overview" in lowered or "repo overview" in lowered:
            return {
                "task_id": "task-1",
                "summary": "write repo overview",
                "file_operations": [
                    {
                        "mode": "write",
                        "path": "REPO_OVERVIEW.md",
                        "content": "# Repo Overview\n\n- Python service code is present.\n- TypeScript web code is present.\n- Go entrypoints are present.\n",
                    }
                ],
                "commands": [],
                "skill_requests": [],
                "notes": ["scripted repo summary"],
            }
        if "change_runbook" in lowered or "commands to validate" in lowered:
            return {
                "task_id": "task-1",
                "summary": "write change runbook",
                "file_operations": [
                    {
                        "mode": "write",
                        "path": "CHANGE_RUNBOOK.md",
                        "content": "# Change Runbook\n\n- Python component: `src/main.py`\n- TypeScript component: `web/app.ts`\n- Go component: `go/cmd/server/main.go`\n\n## Validation commands\n\n- `pytest -q`\n- `npm test`\n- `go test ./...`\n",
                    }
                ],
                "commands": [],
                "skill_requests": [],
                "notes": ["scripted runbook"],
            }
        filename = self._detect_filename(text)
        body = "hello from viki\n"
        if filename.endswith(".md"):
            body = "# Generated by VIKI\n"
        if "internal_note" in lowered:
            filename = "INTERNAL_NOTE.md"
            body = "internal benchmark note\n"
        return {
            "task_id": "task-1",
            "summary": "create requested artifact",
            "file_operations": [{"mode": "write", "path": filename, "content": body}],
            "commands": [],
            "skill_requests": [],
            "notes": [],
        }

    def _debug(self, text: str) -> Dict[str, Any]:
        if "multiply" in text.lower():
            return {
                "summary": "repair calculator bug",
                "root_cause": "addition used instead of multiplication",
                "file_operations": [
                    {"mode": "write", "path": "app/calculator.py", "content": "def multiply(a: int, b: int) -> int:\n    return a * b\n"}
                ],
                "commands": [{"command": "pytest -q tests/test_calculator.py", "timeout": 120}],
                "notes": ["repair path"],
            }
        if "feature_4" in text.lower() or "broken feature" in text.lower():
            return {
                "summary": "repair feature_4 bug",
                "root_cause": "feature_4 uses the wrong arithmetic operation",
                "file_operations": [
                    {"mode": "write", "path": "pkg/feature_4.py", "content": "def feature_4(value):\n    return value + 4\n"}
                ],
                "commands": [{"command": "pytest -q tests/test_feature_4.py", "timeout": 120}],
                "notes": ["repair path"],
            }
        return {"summary": "no repair needed", "root_cause": "none", "file_operations": [], "commands": [], "notes": []}

    def _test(self, text: str) -> Dict[str, Any]:
        lowered = text.lower()
        if "calculator" in lowered:
            commands = [{"command": "pytest -q tests/test_calculator.py", "timeout": 120}]
        elif "account normalization" in lowered or "old helper" in lowered or "commands.py" in lowered:
            commands = [{"command": "pytest -q tests/test_service.py tests/test_cli.py", "timeout": 120}]
        elif "service.py" in lowered or "normalize_user" in lowered or "normalize_account" in lowered:
            commands = [{"command": "pytest -q tests/test_service.py", "timeout": 120}]
        elif "legacy_sum" in lowered or "sum_numbers" in lowered:
            commands = [{"command": "pytest -q tests/test_consumer.py", "timeout": 120}]
        elif "broken feature" in lowered or "feature_4" in lowered:
            commands = [{"command": "pytest -q tests/test_feature_4.py", "timeout": 120}]
        else:
            commands = []
        return {"summary": "scripted validation", "commands": commands, "expected_outputs": []}
