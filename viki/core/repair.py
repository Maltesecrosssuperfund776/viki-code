from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass
class FailureSignal:
    category: str
    severity: str
    summary: str
    command: str
    targeted_tests: List[str]
    rollback_recommended: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FailureClassifier:
    """Digest command failures into actionable repair signals."""

    def classify(self, command_results: Iterable[Dict[str, Any]]) -> List[FailureSignal]:
        signals: List[FailureSignal] = []
        for result in command_results:
            if result.get("returncode") in (0, None):
                continue
            command = result.get("command", "")
            error_text = "\n".join([result.get("error", ""), result.get("output", "")]).lower()
            category = "unknown"
            severity = "medium"
            summary = "unknown failure"
            rollback = False
            targets = self._derive_targets(command, result)

            if "syntaxerror" in error_text or "indentationerror" in error_text:
                category = "syntax"
                severity = "high"
                summary = "syntax-level failure"
            elif "modulenotfounderror" in error_text or "no module named" in error_text:
                category = "dependency"
                severity = "high"
                summary = "missing dependency or import"
                rollback = True
            elif "assert" in error_text or "failed" in error_text or "expected" in error_text:
                category = "test"
                severity = "medium"
                summary = "test assertion failure"
            elif "permission denied" in error_text or result.get("returncode") == 126:
                category = "approval_or_policy"
                severity = "high"
                summary = "policy or approval prevented execution"
            elif "timed out" in error_text or result.get("returncode") == 124:
                category = "timeout"
                severity = "high"
                summary = "command timeout"
                rollback = True
            elif "ruff" in command or "flake" in command or "mypy" in command:
                category = "quality_gate"
                severity = "medium"
                summary = "static check failure"
            elif "pytest" in command:
                category = "test"
                severity = "medium"
                summary = "pytest failure"

            signals.append(
                FailureSignal(
                    category=category,
                    severity=severity,
                    summary=summary,
                    command=command,
                    targeted_tests=targets,
                    rollback_recommended=rollback,
                )
            )
        return signals

    def summarize(self, command_results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        signals = self.classify(command_results)
        categories: Dict[str, int] = {}
        for signal in signals:
            categories[signal.category] = categories.get(signal.category, 0) + 1
        return {
            "count": len(signals),
            "categories": categories,
            "signals": [signal.to_dict() for signal in signals],
        }

    def targeted_rerun_commands(self, command_results: Iterable[Dict[str, Any]], changed_files: Iterable[str]) -> List[Dict[str, Any]]:
        signals = self.classify(command_results)
        reruns: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for signal in signals:
            for target in signal.targeted_tests:
                command = f"pytest -q {target}" if target else "pytest -q"
                if command not in seen:
                    reruns.append({"command": command, "timeout": 120})
                    seen.add(command)
        if not reruns:
            python_targets = [path for path in changed_files if str(path).endswith(".py")]
            if python_targets:
                cmd = "python -m compileall " + " ".join(sorted(python_targets[:10]))
                reruns.append({"command": cmd, "timeout": 120})
        return reruns

    def snapshot_files(self, root: Path, paths: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        snapshot: Dict[str, Dict[str, Any]] = {}
        for relative in sorted(set(str(p) for p in paths)):
            target = (root / relative).resolve()
            exists = target.exists()
            snapshot[relative] = {
                "exists": exists,
                "content": target.read_text(encoding="utf-8", errors="ignore") if exists and target.is_file() else "",
            }
        return snapshot

    def restore_snapshot(self, root: Path, snapshot: Dict[str, Dict[str, Any]]) -> List[str]:
        restored: List[str] = []
        for relative, payload in snapshot.items():
            target = (root / relative).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            if payload.get("exists"):
                target.write_text(payload.get("content", ""), encoding="utf-8")
            elif target.exists():
                target.unlink()
            restored.append(relative)
        return restored

    def improved(self, before: Iterable[Dict[str, Any]], after: Iterable[Dict[str, Any]]) -> bool:
        before_count = sum(1 for item in before if item.get("returncode") not in (0, None))
        after_count = sum(1 for item in after if item.get("returncode") not in (0, None))
        return after_count < before_count

    def _derive_targets(self, command: str, result: Dict[str, Any]) -> List[str]:
        output = "\n".join([result.get("error", ""), result.get("output", "")])
        targets: List[str] = []
        if "pytest" in command:
            for token in output.split():
                cleaned = token.strip(" :,()[]{}\"'")
                if cleaned.startswith("tests/") and ("::" in cleaned or cleaned.endswith(".py")):
                    targets.append(cleaned)
        if not targets and "pytest" in command:
            parts = command.split()
            for part in parts[2:]:
                if part.startswith("tests/") or part.endswith(".py"):
                    targets.append(part)
        return list(dict.fromkeys(targets))
