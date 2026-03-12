from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from viki.evals.stress import generate_stress_repos
from viki.infrastructure.security import SecurityScanner


def wait_for_health(base_url: str, timeout_seconds: int = 45) -> None:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            with urlrequest.urlopen(base_url.rstrip("/") + "/healthz", timeout=5) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - live execution only
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"health check failed: {last_error}")


def post_run(base_url: str, prompt: str, workspace: str) -> tuple[int, dict]:
    payload = json.dumps({"prompt": prompt, "workspace": workspace}).encode("utf-8")
    req = urlrequest.Request(
        base_url.rstrip("/") + "/runs",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=1800) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def run_pytest(repo: Path, target: str, security: SecurityScanner) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--rootdir", ".", target, "-q"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    return {
        "returncode": completed.returncode,
        "stdout": security.redact_text(completed.stdout),
        "stderr": security.redact_text(completed.stderr),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run focused Phase 3 API live validation.")
    parser.add_argument("--workspace", default=".", help="Primary VIKI workspace root")
    parser.add_argument("--output", default="LIVE_RUN_RESULTS/phase3_api_generic", help="Directory for redacted results")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8794)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    security = SecurityScanner()
    manifest = generate_stress_repos(output / "stress_repos")
    (output / "stress_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    base_url = f"http://{args.host}:{args.port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "viki.cli", "up", str(workspace), "--host", args.host, "--port", str(args.port)],
        cwd=str(workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    try:
        wait_for_health(base_url)

        bug_repo = Path(manifest["bug_localization"])
        bug_status, bug_payload = post_run(
            base_url,
            "Fix the multiply bug in this repo, run the relevant tests, and stop with evidence if confidence is too low.",
            str(bug_repo),
        )
        bug_file = (bug_repo / "app" / "calculator.py").read_text(encoding="utf-8")
        bug_validation = run_pytest(bug_repo, "tests/test_calculator.py", security)
        bug_success = bug_status == 200 and bug_validation["returncode"] == 0 and "return a * b" in bug_file
        (output / "api_bugfix.json").write_text(json.dumps({"http_status": bug_status, "payload": bug_payload}, indent=2) + "\n", encoding="utf-8")
        (output / "api_bugfix_validation.json").write_text(
            json.dumps({"success": bug_success, "validation": bug_validation, "calculator": bug_file}, indent=2) + "\n",
            encoding="utf-8",
        )

        monorepo = Path(manifest["monorepo"])
        multi_status, multi_payload = post_run(
            base_url,
            "Refactor normalize_user usage safely across the repo by introducing a normalize_account wrapper, preserving behavior, and running the targeted tests.",
            str(monorepo),
        )
        auth_file = (monorepo / "packages" / "shared" / "auth.py").read_text(encoding="utf-8")
        service_file = (monorepo / "apps" / "api" / "service.py").read_text(encoding="utf-8")
        multi_validation = run_pytest(monorepo, "tests/test_service.py", security)
        multi_success = (
            multi_status == 200
            and multi_validation["returncode"] == 0
            and "def normalize_account" in auth_file
            and "normalize_account" in service_file
        )
        (output / "api_multi_agent.json").write_text(
            json.dumps({"http_status": multi_status, "payload": multi_payload}, indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "api_multi_agent_validation.json").write_text(
            json.dumps(
                {"success": multi_success, "validation": multi_validation, "auth": auth_file, "service": service_file},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        summary = {
            "bugfix_success": bug_success,
            "multi_agent_success": multi_success,
            "bugfix_http_status": bug_status,
            "multi_agent_http_status": multi_status,
            "output_dir": str(output),
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        logs = {
            "stdout": security.redact_text(server.stdout.read() if server.stdout else ""),
            "stderr": security.redact_text(server.stderr.read() if server.stderr else ""),
        }
        (output / "api_server_log.json").write_text(json.dumps(logs, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
