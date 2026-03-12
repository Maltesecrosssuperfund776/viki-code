from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List


@dataclass
class TaskRoute:
    task_id: str
    lane: str
    model: str
    isolation: str
    test_strategy: str
    repair_focus: str
    parallel_safe: bool
    cost_tier: str
    rationale: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskRouter:
    """Heuristic router for task-specific execution plans.

    The goal is not just model selection. It chooses an execution lane,
    isolation posture, repair focus, and test strategy based on the task,
    repo footprint, and user request shape.
    """

    def route_tasks(self, user_request: str, tasks: Iterable[Dict[str, Any]], context: Dict[str, Any]) -> List[TaskRoute]:
        repo_size = len(context.get("existing_files", []))
        routes: List[TaskRoute] = []
        for index, task in enumerate(tasks, start=1):
            routes.append(self._route_single(user_request, task, repo_size, index))
        return routes

    def _route_single(self, user_request: str, task: Dict[str, Any], repo_size: int, index: int) -> TaskRoute:
        text = " ".join(
            [
                user_request or "",
                task.get("title", "") or "",
                task.get("objective", "") or "",
                " ".join(task.get("deliverables", []) or []),
                " ".join(task.get("target_files", []) or []),
            ]
        ).lower()
        rationale: List[str] = []

        lane = "implementation"
        model = "coding"
        isolation = "git-worktree"
        test_strategy = "targeted"
        repair_focus = "incremental"
        parallel_safe = True
        cost_tier = "balanced"

        if any(token in text for token in ["bug", "fix", "error", "failing", "flaky", "regression", "repair"]):
            lane = "repair"
            repair_focus = "root-cause"
            rationale.append("repair-oriented task")
        if any(token in text for token in ["refactor", "rename", "extract", "cleanup", "migrate", "upgrade"]):
            lane = "refactor"
            repair_focus = "safe-structural"
            rationale.append("structural code change")
        if any(token in text for token in ["test", "pytest", "unit test", "integration test"]):
            test_strategy = "full"
            rationale.append("testing-heavy task")
        if any(token in text for token in ["ci", "docker", "infra", "workflow", "deploy", "terraform", "kubernetes"]):
            isolation = "sandboxed-worktree"
            parallel_safe = False
            rationale.append("infrastructure-sensitive task")
        if any(token in text for token in ["security", "secret", "credential", "auth", "permission", "sandbox"]):
            model = "reasoning"
            isolation = "sandboxed-worktree"
            repair_focus = "policy-first"
            parallel_safe = False
            rationale.append("security-sensitive task")
        if any(token in text for token in ["large", "monorepo", "repo-wide", "across the repo"]) or repo_size > 250:
            model = "reasoning"
            cost_tier = "high-confidence"
            rationale.append("large-repo planning bias")
        if any(token in text for token in ["latency", "quick", "small", "simple"]):
            cost_tier = "fast"
            rationale.append("latency-biased route")
        if any(token in text for token in ["migration", "schema", "api contract", "sdk", "protocol"]):
            model = "reasoning"
            repair_focus = "checkpointed"
            parallel_safe = False
            rationale.append("contract-sensitive change")

        target_files = task.get("target_files", []) or []
        wide_refactor = any(token in text for token in ["repo-wide", "across the repo", "monorepo", "multiple packages"])
        if lane == "refactor":
            if wide_refactor or repo_size > 250 or len(target_files) > 3:
                model = "reasoning"
                rationale.append("wide structural change")
            else:
                model = "coding"
                rationale.append("localized structural change")
        if len(target_files) > 5:
            parallel_safe = False
            test_strategy = "full"
            rationale.append("wide file fan-out")
        if any(path.endswith((".md", ".txt", ".rst")) for path in target_files) and len(target_files) == len([p for p in target_files if p.endswith((".md", ".txt", ".rst"))]):
            model = "fast"
            cost_tier = "fast"
            rationale.append("docs-only edit")

        return TaskRoute(
            task_id=task.get("id") or f"task-{index}",
            lane=lane,
            model=model,
            isolation=isolation,
            test_strategy=test_strategy,
            repair_focus=repair_focus,
            parallel_safe=parallel_safe,
            cost_tier=cost_tier,
            rationale=rationale or ["default balanced route"],
        )
