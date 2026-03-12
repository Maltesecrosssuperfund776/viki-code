from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict
from urllib import request as urlrequest

from ..api.client import VikiClient
from ..infrastructure.security import SecurityScanner
from .stress import generate_stress_repos


class LiveExecutionSuite:
    def __init__(self, workspace: str | Path, results_dir: str | Path):
        self.workspace = Path(workspace).resolve()
        self.results_dir = Path(results_dir).resolve()
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.security = SecurityScanner()

    def _write_json(self, name: str, payload: Dict[str, Any]) -> None:
        (self.results_dir / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _run_cli(self, *args: str) -> Dict[str, Any]:
        command = [sys.executable, "-m", "viki.cli", *args]
        completed = subprocess.run(command, cwd=str(self.workspace), capture_output=True, text=True, timeout=900, env=os.environ.copy())
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": self.security.redact_text(completed.stdout),
            "stderr": self.security.redact_text(completed.stderr),
        }

    def _prepare_workspace(self, repo: Path) -> Dict[str, Any]:
        return self._run_cli("up", str(repo), "--dry-run")

    def _step_result(self, name: str, callback: Callable[[], Any]) -> Dict[str, Any]:
        started = time.time()
        try:
            payload = callback()
            return {
                "name": name,
                "status": "completed",
                "duration_seconds": round(time.time() - started, 3),
                "payload": payload,
            }
        except Exception as exc:  # pragma: no cover - exercised in live run
            return {
                "name": name,
                "status": "failed",
                "duration_seconds": round(time.time() - started, 3),
                "error": self.security.redact_text(str(exc)),
            }

    def _wait_for_api(self, base_url: str, timeout_seconds: int = 45) -> None:
        deadline = time.time() + timeout_seconds
        last_error = None
        while time.time() < deadline:
            try:
                with urlrequest.urlopen(base_url.rstrip("/") + "/healthz", timeout=5) as response:
                    if response.status == 200:
                        return
            except Exception as exc:  # pragma: no cover - exercised in live run
                last_error = exc
                time.sleep(1)
        raise RuntimeError(f"VIKI API did not become healthy in time: {last_error}")

    def run(self, api_host: str = "127.0.0.1", api_port: int = 8787) -> Dict[str, Any]:
        stress_root = self.results_dir / "stress_repos"
        manifest = generate_stress_repos(stress_root)
        self._write_json("stress_manifest.json", manifest)

        bug_repo = Path(manifest["bug_localization"])
        monorepo = Path(manifest["monorepo"])
        base_url = f"http://{api_host}:{api_port}"

        preparations = {
            "workspace": self._prepare_workspace(self.workspace),
            "bug_repo": self._prepare_workspace(bug_repo),
            "monorepo": self._prepare_workspace(monorepo),
        }
        self._write_json("preparation.json", preparations)

        cli_smoke = self._run_cli(
            "run",
            "Create LIVE_SMOKE.md containing exactly one line: live smoke ok. Validate using Python, not shell builtins.",
            "--path",
            str(self.workspace),
        )
        self._write_json("cli_smoke.json", cli_smoke)
        api_smoke: Dict[str, Any] = {"status": "not_started"}
        repo_context: Dict[str, Any] = {"status": "not_started"}
        live_fix: Dict[str, Any] = {"status": "not_started"}
        multi_agent: Dict[str, Any] = {"status": "not_started"}

        server = subprocess.Popen(
            [sys.executable, "-m", "viki.cli", "up", str(self.workspace), "--host", api_host, "--port", str(api_port)],
            cwd=str(self.workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=os.environ.copy(),
        )
        try:
            self._wait_for_api(base_url)
            client = VikiClient(base_url=base_url, timeout=1800)
            api_smoke = self._step_result(
                "api_smoke",
                lambda: client.run(
                    "Create LIVE_API_SMOKE.md containing exactly one line: live api smoke ok. Validate using Python, not shell builtins.",
                    workspace=str(self.workspace),
                ),
            )
            repo_context = self._step_result("repo_context", lambda: client.repo_context("multiply bug", limit=8))
            live_fix = self._step_result(
                "live_fix",
                lambda: client.run(
                    "Fix the multiply bug, run the relevant tests, and stop with evidence if confidence is too low.",
                    workspace=str(bug_repo),
                ),
            )
            multi_agent = self._step_result(
                "multi_agent",
                lambda: client.run(
                    "Refactor normalize_user usage safely across the repo, preserve behavior, and run the targeted tests.",
                    workspace=str(monorepo),
                ),
            )
            api_payload = {
                "api_smoke": api_smoke,
                "repo_context": repo_context,
                "live_fix": live_fix,
                "multi_agent": multi_agent,
            }
            self._write_json("api_live_results.json", api_payload)
            for name, payload in api_payload.items():
                if isinstance(payload, dict):
                    self._write_json(f"{name}.json", payload)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
            stdout = self.security.redact_text(server.stdout.read() if server.stdout else "")
            stderr = self.security.redact_text(server.stderr.read() if server.stderr else "")
            self._write_json("api_server_log.json", {"stdout": stdout, "stderr": stderr})

        summary = {
            "cli_smoke_returncode": cli_smoke["returncode"],
            "preparations": {name: result["returncode"] for name, result in preparations.items()},
            "api_status": {
                "api_smoke": api_smoke.get("status") if isinstance(api_smoke, dict) else "unknown",
                "repo_context": repo_context.get("status") if isinstance(repo_context, dict) else "unknown",
                "live_fix": live_fix.get("status") if isinstance(live_fix, dict) else "unknown",
                "multi_agent": multi_agent.get("status") if isinstance(multi_agent, dict) else "unknown",
            },
            "stress_repos": manifest,
            "results_dir": str(self.results_dir),
        }
        self._write_json("summary.json", summary)
        return summary
