from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from viki.api.server import create_app
from viki.core.repair import FailureClassifier
from viki.core.routing import TaskRouter
from viki.skills.factory import AutoSkillFactory
from viki.skills.registry import SkillRegistry


def test_task_router_picks_repair_lane_for_flaky_bugfix():
    router = TaskRouter()
    routes = router.route_tasks(
        "Fix flaky pytest regression in CI",
        [{"id": "task-1", "title": "repair flaky test", "objective": "fix failing flaky regression in CI", "target_files": ["tests/test_ci.py"]}],
        {"existing_files": [f"file_{i}.py" for i in range(300)]},
    )
    route = routes[0]
    assert route.lane == "repair"
    assert route.model == "reasoning"
    assert route.parallel_safe is False


def test_failure_classifier_extracts_targeted_pytest_reruns():
    classifier = FailureClassifier()
    failures = [
        {
            "command": "pytest -q",
            "returncode": 1,
            "output": "FAILED tests/test_api.py::test_healthz - assert 500 == 200",
            "error": "",
        }
    ]
    summary = classifier.summarize(failures)
    reruns = classifier.targeted_rerun_commands(failures, ["viki/api/server.py"])
    assert summary["categories"]["test"] == 1
    assert reruns[0]["command"] == "pytest -q tests/test_api.py::test_healthz"


def test_skill_manifest_checksum_is_verified(tmp_path: Path):
    factory = AutoSkillFactory(tmp_path, provider=None)

    async def run_test():
        await factory.create_skill("Create checksum verified skill", preferred_name="checksum_skill")

    import asyncio

    asyncio.run(run_test())
    registry = SkillRegistry(tmp_path)
    skill = next(item for item in registry.list_skills() if item.name == "checksum_skill")
    assert skill.checksum
    assert skill.integrity == "verified"


def test_api_protocol_endpoint_exposes_run_contract(tmp_path: Path):
    (tmp_path / ".viki-workspace").mkdir()
    app = create_app(tmp_path)
    client = TestClient(app)
    response = client.get("/protocol")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "viki-agent-protocol"
    assert payload["capabilities"]["resume"] is True


def test_task_router_uses_coding_model_for_localized_refactor():
    router = TaskRouter()
    routes = router.route_tasks(
        "Refactor auth naming safely in this package and keep tests green",
        [
            {
                "id": "task-1",
                "title": "rename auth helper",
                "objective": "introduce normalize_account as a wrapper and update the local caller",
                "target_files": ["packages/shared/auth.py", "apps/api/service.py", "tests/test_service.py"],
            }
        ],
        {"existing_files": [f"file_{index}.py" for index in range(40)]},
    )
    assert routes[0].lane == "refactor"
    assert routes[0].model == "coding"
