from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from viki.evals.suite import BenchmarkSuite, EvalCheck
from viki.skills.factory import AutoSkillFactory
from viki.skills.registry import SkillRegistry


class BenchmarkProvider:
    def validate_config(self):
        return True

    def get_available_models(self):
        return ["fake/reasoning", "fake/coding"]

    async def complete(self, model, messages, **kwargs):
        system = messages[0]["content"].lower()
        joined = "\n".join(str(item.get("content", "")) for item in messages)
        if "planning swarm" in system:
            content = '''{
              "goal": "benchmark goal",
              "summary": "single task plan",
              "tasks": [
                {
                  "id": "task-1",
                  "title": "write benchmark artifact",
                  "objective": "write benchmark artifact",
                  "target_files": ["hello.txt"],
                  "deliverables": ["benchmark artifact"],
                  "commands": [],
                  "skill_requests": []
                }
              ],
              "testing_commands": [],
              "acceptance_criteria": ["artifact exists"]
            }'''
        elif "coding swarm" in system:
            if "internal_note" in joined.lower() or "INTERNAL_NOTE.md" in joined:
                file_name = "INTERNAL_NOTE.md"
                content_text = "internal benchmark note\n"
            else:
                file_name = "hello.txt"
                content_text = "hello from benchmark\n"
            content = json.dumps(
                {
                    "task_id": "task-1",
                    "summary": "created file",
                    "file_operations": [{"mode": "write", "path": file_name, "content": content_text}],
                    "commands": [],
                    "skill_requests": [],
                    "notes": [],
                }
            )
        elif "testing swarm" in system:
            content = '{"summary": "tests ok", "commands": [], "expected_outputs": []}'
        elif "debugging swarm" in system:
            content = '{"summary": "no repair needed", "root_cause": "none", "file_operations": [], "commands": [], "notes": []}'
        else:
            content = '{"summary": "security ok", "issues": [], "recommended_commands": []}'
        return {
            "content": content,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": model or "fake",
            "provider": "fake",
        }


def test_skill_permissions_are_enforced(tmp_path: Path):
    factory = AutoSkillFactory(tmp_path, provider=None)

    async def build():
        await factory.create_skill("Write a note file", preferred_name="writer", template="patch_writer")

    asyncio.run(build())
    registry = SkillRegistry(tmp_path)
    with pytest.raises(PermissionError):
        registry.invoke(
            "writer",
            {"path": "note.txt", "content": "blocked\n"},
            {"workspace": str(tmp_path), "allowed_permissions": ["workspace:read"]},
        )


def test_skill_isolation_writes_back_changed_files(tmp_path: Path):
    factory = AutoSkillFactory(tmp_path, provider=None)

    async def build():
        await factory.create_skill("Write a note file", preferred_name="writer", template="patch_writer")

    asyncio.run(build())
    registry = SkillRegistry(tmp_path)
    result = registry.invoke(
        "writer",
        {"path": "note.txt", "content": "hello\n"},
        {"workspace": str(tmp_path), "allowed_permissions": ["workspace:read", "workspace:write"]},
    )
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello\n"
    assert "note.txt" in result.get("changed_files", [])


def test_skill_dependency_validation_and_env_prepare(tmp_path: Path):
    factory = AutoSkillFactory(tmp_path, provider=None)

    async def build():
        await factory.create_skill("Read repo", preferred_name="reader", template="workspace_reader")

    asyncio.run(build())
    registry = SkillRegistry(tmp_path)
    prepared = registry.prepare_environment("reader")
    assert Path(prepared["python"]).exists()

    async def build_invalid():
        await factory.create_skill(
            "Invalid dep skill",
            preferred_name="bad_dep",
            template="workspace_reader",
            dependencies=["requests"],
        )

    with pytest.raises(ValueError):
        asyncio.run(build_invalid())


def test_benchmark_suite_load_run_compare_and_publish(tmp_path: Path):
    cases_root = tmp_path / "cases"
    (cases_root / "public" / "case_one" / "fixture").mkdir(parents=True)
    (cases_root / "private" / "case_two" / "fixture").mkdir(parents=True)
    (cases_root / "public" / "case_one" / "case.yaml").write_text(
        """
name: create-hello
prompt: create hello.txt with the text hello from benchmark
fixture_dir: fixture
dataset: public
checks:
  - type: file_exists
    path: hello.txt
  - type: file_contains
    path: hello.txt
    text: hello
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (cases_root / "private" / "case_two" / "case.yaml").write_text(
        """
name: internal-note
prompt: create INTERNAL_NOTE.md with one line summary
fixture_dir: fixture
dataset: private
checks:
  - type: file_exists
    path: INTERNAL_NOTE.md
""".strip()
        + "\n",
        encoding="utf-8",
    )
    cases = BenchmarkSuite.load_cases(tmp_path, datasets=["public", "private"], cases_dir=cases_root)
    assert {case.dataset for case in cases} == {"public", "private"}

    suite = BenchmarkSuite(tmp_path, BenchmarkProvider(), cases=cases, agent_name="VIKI Code")
    report = asyncio.run(suite.run())
    assert report["summary"]["passed"] == 2
    report_path = BenchmarkSuite.save_report(tmp_path, report)
    baseline = dict(report)
    baseline["summary"] = dict(report["summary"])
    baseline["summary"]["agent"] = "Codex"
    baseline["summary"]["task_completion_rate"] = 0.5
    baseline["summary"]["pass_at_1"] = 0.5
    comparison = BenchmarkSuite.compare_reports(report, {"codex": baseline})
    assert comparison["baselines"][0]["task_completion_rate_delta"] == 0.5
    comparison_path = BenchmarkSuite.save_comparison(tmp_path, comparison)
    published = BenchmarkSuite.publish_board(tmp_path, report, comparison=comparison, output_dir=tmp_path / "docs" / "benchmarks")
    assert report_path.exists()
    assert comparison_path.exists()
    assert (published / "index.md").exists()


def test_benchmark_supports_file_contains_any(tmp_path: Path):
    case_root = tmp_path / "case"
    case_root.mkdir()
    (case_root / "CHANGE_RUNBOOK.md").write_text("Use npx ts-node and go run go/cmd/server/main.go\n", encoding="utf-8")
    result = BenchmarkSuite._evaluate_check(
        case_root,
        EvalCheck(type="file_contains_any", path="CHANGE_RUNBOOK.md", texts=["npm test", "npx ts-node"]),
    )
    assert result["passed"] is True
