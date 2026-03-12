from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from ..config import settings
from ..core.hive import HiveMind


@dataclass
class EvalCheck:
    type: str
    path: str | None = None
    text: str | None = None
    texts: list[str] | None = None
    command: str | None = None
    timeout: int = 60


@dataclass
class EvalCase:
    name: str
    prompt: str
    dataset: str = "public"
    fixture_dir: Path | None = None
    checks: list[EvalCheck] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


DEFAULT_CASES = [
    EvalCase(
        name="hello-file",
        prompt="create hello file",
        checks=[EvalCheck(type="file_exists", path="hello.txt")],
    ),
    EvalCase(
        name="readme-touch",
        prompt="create README_CHANGELOG.md with one line summary",
        checks=[EvalCheck(type="file_exists", path="README_CHANGELOG.md")],
    ),
]


class BenchmarkSuite:
    def __init__(
        self,
        workspace: str | Path,
        provider: Any,
        cases: List[EvalCase] | None = None,
        agent_name: str = "VIKI Code",
    ):
        self.workspace = Path(workspace).resolve()
        self.provider = provider
        self.cases = cases or DEFAULT_CASES
        self.agent_name = agent_name

    @staticmethod
    def _copy_fixture(source: Path, target: Path) -> None:
        if not source.exists():
            return
        shutil.copytree(source, target, dirs_exist_ok=True)

    @staticmethod
    def _default_cases_dir(workspace: Path) -> Path:
        candidate = workspace / "benchmarks"
        if candidate.exists():
            return candidate
        return Path(__file__).resolve().parents[2] / "benchmarks"

    @classmethod
    def load_cases(
        cls,
        workspace: str | Path,
        datasets: Iterable[str] | None = None,
        cases_dir: str | Path | None = None,
    ) -> list[EvalCase]:
        workspace_path = Path(workspace).resolve()
        root = Path(cases_dir).resolve() if cases_dir else cls._default_cases_dir(workspace_path)
        wanted = list(datasets or ["public"])
        loaded: list[EvalCase] = []
        for dataset in wanted:
            dataset_root = root / dataset
            if not dataset_root.exists():
                continue
            for manifest_path in sorted(dataset_root.rglob("case.yaml")):
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                fixture = raw.get("fixture_dir")
                checks = [EvalCheck(**item) for item in raw.get("checks", [])]
                loaded.append(
                    EvalCase(
                        name=raw.get("name") or manifest_path.parent.name,
                        prompt=raw["prompt"],
                        dataset=raw.get("dataset", dataset),
                        fixture_dir=(manifest_path.parent / fixture).resolve() if fixture else None,
                        checks=checks,
                        metadata=raw.get("metadata", {}),
                        source=str(manifest_path),
                    )
                )
        return loaded

    @staticmethod
    def _evaluate_check(case_root: Path, check: EvalCheck) -> dict[str, Any]:
        if check.type == "file_exists":
            path = case_root / str(check.path or "")
            return {"type": check.type, "passed": path.exists(), "path": str(check.path or "")}
        if check.type == "file_contains":
            path = case_root / str(check.path or "")
            if not path.exists():
                return {"type": check.type, "passed": False, "path": str(check.path or ""), "reason": "missing file"}
            content = path.read_text(encoding="utf-8", errors="ignore")
            return {"type": check.type, "passed": str(check.text or "") in content, "path": str(check.path or ""), "text": check.text}
        if check.type == "file_contains_any":
            path = case_root / str(check.path or "")
            if not path.exists():
                return {"type": check.type, "passed": False, "path": str(check.path or ""), "reason": "missing file"}
            content = path.read_text(encoding="utf-8", errors="ignore")
            options = list(check.texts or [])
            passed = any(option in content for option in options)
            return {"type": check.type, "passed": passed, "path": str(check.path or ""), "texts": options}
        if check.type == "command_exit_zero":
            completed = subprocess.run(
                str(check.command or ""),
                cwd=str(case_root),
                capture_output=True,
                text=True,
                timeout=check.timeout,
                shell=True,
            )
            return {
                "type": check.type,
                "passed": completed.returncode == 0,
                "command": check.command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[:800],
                "stderr": completed.stderr[:800],
            }
        if check.type == "session_status":
            session_path = case_root / ".viki-workspace" / "latest_result.json"
            if not session_path.exists():
                return {"type": check.type, "passed": False, "reason": "missing latest_result.json"}
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            expected = str(check.text or "completed")
            actual = str(payload.get("status", ""))
            return {"type": check.type, "passed": actual == expected, "expected": expected, "actual": actual}
        raise ValueError(f"unsupported benchmark check: {check.type}")

    async def run(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {"workspace": str(self.workspace), "agent": self.agent_name, "cases": []}
        durations: List[float] = []
        datasets: dict[str, int] = {}
        for case in self.cases:
            case_root = self.workspace / settings.benchmark_dir / case.dataset / case.name
            if case_root.exists():
                shutil.rmtree(case_root)
            case_root.mkdir(parents=True, exist_ok=True)
            (case_root / settings.workspace_dir).mkdir(parents=True, exist_ok=True)
            if case.fixture_dir:
                self._copy_fixture(case.fixture_dir, case_root)
            hive = HiveMind(self.provider, str(case_root))
            await hive.initialize()
            try:
                started = time.perf_counter()
                result = await hive.process_request(case.prompt)
                elapsed = time.perf_counter() - started
            finally:
                await hive.shutdown()
            artifacts_dir = case_root / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            (case_root / settings.workspace_dir / "latest_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            (artifacts_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            (artifacts_dir / "commands.json").write_text(json.dumps(result.get("commands", []), indent=2) + "\n", encoding="utf-8")
            (artifacts_dir / "diff_preview.json").write_text(json.dumps(result.get("diff_preview", []), indent=2) + "\n", encoding="utf-8")
            (artifacts_dir / "task_ledgers.json").write_text(json.dumps(result.get("task_ledgers", []), indent=2) + "\n", encoding="utf-8")
            durations.append(elapsed)
            datasets[case.dataset] = datasets.get(case.dataset, 0) + 1
            check_results = [self._evaluate_check(case_root, check) for check in case.checks]
            passed = all(item["passed"] for item in check_results)
            failed_commands = [item for item in result.get("commands", []) if item.get("returncode") not in (0, None)]
            case_score = 1.0 if passed else 0.0
            case_score -= min(0.3, len(failed_commands) * 0.05)
            case_score -= min(0.2, len(result.get("pending_approvals", [])) * 0.05)
            case_score = max(0.0, round(case_score, 3))
            report["cases"].append(
                {
                    "name": case.name,
                    "dataset": case.dataset,
                    "passed": passed,
                    "checks": check_results,
                    "session_id": result["session_id"],
                    "changed_files": result["changed_files"],
                    "status": result["status"],
                    "time_to_green_seconds": round(elapsed, 3),
                    "pending_approvals": len(result.get("pending_approvals", [])),
                    "failed_command_count": len(failed_commands),
                    "repair_attempts": sum(len(item.get("repairs", [])) for item in result.get("task_results", [])) if isinstance(result.get("task_results"), list) else 0,
                    "merge_conflict_count": sum(len(item.get("merge_conflicts", [])) for item in result.get("merge_summary", []) if isinstance(item, dict)),
                    "confidence": max((float(item.get("confidence", 0.0) or 0.0) for item in result.get("task_results", []) or []), default=0.0),
                    "score": case_score,
                    "artifacts_dir": str(artifacts_dir),
                    "source": case.source,
                    "metadata": case.metadata,
                }
            )
        passed_cases = [item for item in report["cases"] if item["passed"]]
        long_case_count = sum(1 for duration in durations if duration > 5)
        report["summary"] = {
            "agent": self.agent_name,
            "total": len(report["cases"]),
            "passed": len(passed_cases),
            "datasets": datasets,
            "task_completion_rate": round(len(passed_cases) / max(len(report["cases"]), 1), 4),
            "pass_at_1": round(len(passed_cases) / max(len(report["cases"]), 1), 4),
            "median_time_to_green": round(statistics.median(durations), 3) if durations else 0.0,
            "mean_case_score": round(sum(item.get("score", 0.0) for item in report["cases"]) / max(len(report["cases"]), 1), 4),
            "long_task_completion_rate": round(sum(1 for duration, case in zip(durations, report["cases"]) if duration > 5 and case["passed"]) / max(long_case_count, 1), 4) if durations else 0.0,
            "security_approval_incidents": sum(item["pending_approvals"] for item in report["cases"]),
            "revert_rate": 0.0,
            "human_review_acceptance": None,
            "cost_per_solved_task": None,
        }
        return report

    @staticmethod
    def compare_reports(subject: Dict[str, Any], baselines: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        subject_summary = subject.get("summary", {})
        subject_rate = float(subject_summary.get("task_completion_rate", 0.0) or 0.0)
        subject_time = float(subject_summary.get("median_time_to_green", 0.0) or 0.0)
        comparisons = []
        for name, report in baselines.items():
            summary = report.get("summary", {})
            baseline_rate = float(summary.get("task_completion_rate", 0.0) or 0.0)
            baseline_time = float(summary.get("median_time_to_green", 0.0) or 0.0)
            comparisons.append(
                {
                    "baseline": name,
                    "baseline_agent": summary.get("agent") or report.get("agent") or name,
                    "task_completion_rate_delta": round(subject_rate - baseline_rate, 4),
                    "pass_at_1_delta": round(float(subject_summary.get("pass_at_1", 0.0) or 0.0) - float(summary.get("pass_at_1", 0.0) or 0.0), 4),
                    "median_time_to_green_delta": round(baseline_time - subject_time, 3),
                    "subject": {"task_completion_rate": subject_rate, "median_time_to_green": subject_time},
                    "baseline_metrics": {"task_completion_rate": baseline_rate, "median_time_to_green": baseline_time},
                }
            )
        return {
            "subject_agent": subject_summary.get("agent") or subject.get("agent") or "VIKI Code",
            "subject_report": subject,
            "baselines": comparisons,
        }

    @staticmethod
    def save_report(workspace: str | Path, report: Dict[str, Any], name: str = "latest_report.json") -> Path:
        path = Path(workspace).resolve() / settings.benchmark_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        markdown = path.with_suffix(".md")
        summary = report.get("summary", {})
        markdown.write_text(
            "\n".join(
                [
                    f"# {summary.get('agent', report.get('agent', 'VIKI Code'))} Benchmark Board",
                    "",
                    f"- Total cases: {summary.get('total', 0)}",
                    f"- Passed: {summary.get('passed', 0)}",
                    f"- Task completion rate: {summary.get('task_completion_rate', 0)}",
                    f"- Pass@1: {summary.get('pass_at_1', 0)}",
                    f"- Median time to green: {summary.get('median_time_to_green', 0)}s",
                    f"- Mean case score: {summary.get('mean_case_score', 0)}",
                    f"- Security/approval incidents: {summary.get('security_approval_incidents', 0)}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def save_comparison(workspace: str | Path, comparison: Dict[str, Any], name: str = "latest_comparison.json") -> Path:
        path = Path(workspace).resolve() / settings.benchmark_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
        markdown = path.with_suffix(".md")
        lines = [f"# Head-to-head proof for {comparison.get('subject_agent', 'VIKI Code')}", ""]
        for item in comparison.get("baselines", []):
            lines.extend(
                [
                    f"## vs {item.get('baseline_agent', item.get('baseline', 'baseline'))}",
                    f"- Task completion rate delta: {item.get('task_completion_rate_delta', 0)}",
                    f"- Pass@1 delta: {item.get('pass_at_1_delta', 0)}",
                    f"- Median time-to-green delta: {item.get('median_time_to_green_delta', 0)}",
                    "",
                ]
            )
        markdown.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return path

    @staticmethod
    def publish_board(workspace: str | Path, report: Dict[str, Any], comparison: Dict[str, Any] | None = None, output_dir: str | Path | None = None) -> Path:
        destination = Path(output_dir).resolve() if output_dir else Path(workspace).resolve() / "docs" / "benchmarks"
        destination.mkdir(parents=True, exist_ok=True)
        report_path = destination / "report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if comparison is not None:
            (destination / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
        lines = [f"# {report.get('summary', {}).get('agent', report.get('agent', 'VIKI Code'))} benchmark board", ""]
        lines.append(f"- Cases: {report.get('summary', {}).get('total', 0)}")
        lines.append(f"- Passed: {report.get('summary', {}).get('passed', 0)}")
        lines.append(f"- Task completion rate: {report.get('summary', {}).get('task_completion_rate', 0)}")
        lines.append(f"- Pass@1: {report.get('summary', {}).get('pass_at_1', 0)}")
        lines.append(f"- Mean case score: {report.get('summary', {}).get('mean_case_score', 0)}")
        lines.append("")
        if comparison is not None:
            lines.append("## Head-to-head")
            lines.append("")
            for item in comparison.get("baselines", []):
                lines.append(f"### vs {item.get('baseline_agent', item.get('baseline', 'baseline'))}")
                lines.append(f"- Task completion rate delta: {item.get('task_completion_rate_delta', 0)}")
                lines.append(f"- Pass@1 delta: {item.get('pass_at_1_delta', 0)}")
                lines.append(f"- Median time-to-green delta: {item.get('median_time_to_green_delta', 0)}")
                lines.append("")
        (destination / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return destination
