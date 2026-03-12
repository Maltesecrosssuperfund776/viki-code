from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from viki.infrastructure.security import SecurityScanner


def copy_fixture(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


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
    try:
        with urlrequest.urlopen(req, timeout=2400) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:  # pragma: no cover - live execution only
        body = exc.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {"raw": body}
        return exc.code, payload


def get_json(base_url: str, path: str) -> dict:
    with urlrequest.urlopen(base_url.rstrip("/") + path, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def run_cli(prompt: str, workspace: Path, security: SecurityScanner) -> dict:
    prepare = subprocess.run(
        [sys.executable, "-m", "viki.cli", "up", str(workspace), "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env=os.environ.copy(),
    )
    completed = subprocess.run(
        [sys.executable, "-m", "viki.cli", "run", prompt, "--path", str(workspace)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=2400,
        env=os.environ.copy(),
    )
    session_match = re.search(r"Session\s+(\d{8}-\d{6})", completed.stdout)
    return {
        "prepare_returncode": prepare.returncode,
        "prepare_stdout": security.redact_text(prepare.stdout),
        "prepare_stderr": security.redact_text(prepare.stderr),
        "returncode": completed.returncode,
        "session_id": session_match.group(1) if session_match else None,
        "stdout": security.redact_text(completed.stdout),
        "stderr": security.redact_text(completed.stderr),
    }


def run_pytest(repo: Path, targets: list[str], security: SecurityScanner) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--rootdir", ".", *targets, "-q"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    return {
        "returncode": completed.returncode,
        "stdout": security.redact_text(completed.stdout),
        "stderr": security.redact_text(completed.stderr),
    }


def validate_file_contains(repo: Path, path: str, *needles: str) -> dict:
    target = repo / path
    if not target.exists():
        return {"path": path, "exists": False, "contains": {needle: False for needle in needles}}
    content = target.read_text(encoding="utf-8", errors="ignore")
    return {"path": path, "exists": True, "contains": {needle: (needle in content) for needle in needles}}


def validate_file_contains_any(repo: Path, path: str, groups: dict[str, list[str]]) -> dict:
    target = repo / path
    if not target.exists():
        return {"path": path, "exists": False, "contains_any": {key: False for key in groups}}
    content = target.read_text(encoding="utf-8", errors="ignore")
    return {
        "path": path,
        "exists": True,
        "contains_any": {
            key: any(option in content for option in options)
            for key, options in groups.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the broader public-release live suite.")
    parser.add_argument("--workspace", default=".", help="Primary VIKI workspace root")
    parser.add_argument("--output", default="LIVE_RUN_RESULTS/public_release", help="Directory for redacted live results")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8798)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    security = SecurityScanner()

    fixtures = {
        "api_bugfix_repo": ROOT / "benchmarks" / "public" / "generic_bugfix" / "fixture",
        "api_refactor_repo": ROOT / "benchmarks" / "public" / "generic_refactor" / "fixture",
        "cli_bugfix_repo": ROOT / "benchmarks" / "public" / "generic_bugfix" / "fixture",
        "cli_refactor_repo": ROOT / "benchmarks" / "public" / "generic_refactor" / "fixture",
        "cli_migration_repo": ROOT / "benchmarks" / "public" / "generic_migration" / "fixture",
        "cli_repo_overview_repo": ROOT / "benchmarks" / "public" / "repo_overview" / "fixture",
        "cli_matrix_bugfix_repo": ROOT / "benchmarks" / "public" / "matrix_bugfix" / "fixture",
        "cli_change_runbook_repo": ROOT / "benchmarks" / "public" / "change_runbook" / "fixture",
        "cli_big_rollout_repo": ROOT / "benchmarks" / "public" / "monorepo_rollout" / "fixture",
    }
    manifest: dict[str, str] = {}
    for name, source in fixtures.items():
        target = output / name
        copy_fixture(source, target)
        manifest[name] = str(target)
    (output / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    base_url = f"http://{args.host}:{args.port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "viki.cli", "up", str(workspace), "--host", args.host, "--port", str(args.port)],
        cwd=str(workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    summary: dict[str, object] = {}
    try:
        wait_for_health(base_url)
        matrix_context = get_json(base_url, "/repo/context?q=broken+feature+repo&limit=8")
        rollout_context = get_json(base_url, "/repo/context?q=account+normalization+monorepo&limit=8")
        (output / "matrix_context.json").write_text(json.dumps(matrix_context, indent=2) + "\n", encoding="utf-8")
        (output / "rollout_context.json").write_text(json.dumps(rollout_context, indent=2) + "\n", encoding="utf-8")

        api_bugfix_repo = Path(manifest["api_bugfix_repo"])
        api_bugfix_status, api_bugfix_payload = post_run(
            base_url,
            "Fix the multiply bug in this repo, run the relevant tests, and stop with evidence if confidence is too low.",
            str(api_bugfix_repo),
        )
        api_bugfix_validation = {
            "pytest": run_pytest(api_bugfix_repo, ["tests/test_calculator.py"], security),
            "file": validate_file_contains(api_bugfix_repo, "app/calculator.py", "return a * b"),
        }
        api_bugfix_success = api_bugfix_status == 200 and api_bugfix_validation["pytest"]["returncode"] == 0 and api_bugfix_validation["file"]["contains"]["return a * b"]
        (output / "api_bugfix.json").write_text(json.dumps({"http_status": api_bugfix_status, "payload": api_bugfix_payload, "validation": api_bugfix_validation, "success": api_bugfix_success}, indent=2) + "\n", encoding="utf-8")

        api_refactor_repo = Path(manifest["api_refactor_repo"])
        api_refactor_status, api_refactor_payload = post_run(
            base_url,
            "Refactor normalize_user usage safely across the repo by introducing a normalize_account wrapper, preserving behavior, and running the targeted tests.",
            str(api_refactor_repo),
        )
        api_refactor_validation = {
            "pytest": run_pytest(api_refactor_repo, ["tests/test_service.py"], security),
            "auth": validate_file_contains(api_refactor_repo, "packages/shared/auth.py", "def normalize_account"),
            "service": validate_file_contains(api_refactor_repo, "apps/api/service.py", "normalize_account"),
        }
        api_refactor_success = api_refactor_status == 200 and api_refactor_validation["pytest"]["returncode"] == 0 and api_refactor_validation["auth"]["contains"]["def normalize_account"] and api_refactor_validation["service"]["contains"]["normalize_account"]
        (output / "api_multi_agent.json").write_text(json.dumps({"http_status": api_refactor_status, "payload": api_refactor_payload, "validation": api_refactor_validation, "success": api_refactor_success}, indent=2) + "\n", encoding="utf-8")

        cli_tasks = [
            {
                "name": "cli_bugfix",
                "repo": Path(manifest["cli_bugfix_repo"]),
                "prompt": "Fix the multiply bug in this repo, run the relevant tests, and stop with evidence if confidence is too low.",
                "validator": lambda repo: {
                    "pytest": run_pytest(repo, ["tests/test_calculator.py"], security),
                    "file": validate_file_contains(repo, "app/calculator.py", "return a * b"),
                },
                "success": lambda payload: payload["pytest"]["returncode"] == 0 and payload["file"]["contains"]["return a * b"],
            },
            {
                "name": "cli_refactor",
                "repo": Path(manifest["cli_refactor_repo"]),
                "prompt": "Refactor normalize_user usage safely across the repo by introducing a normalize_account wrapper, preserving behavior, and running the targeted tests.",
                "validator": lambda repo: {
                    "pytest": run_pytest(repo, ["tests/test_service.py"], security),
                    "auth": validate_file_contains(repo, "packages/shared/auth.py", "def normalize_account"),
                    "service": validate_file_contains(repo, "apps/api/service.py", "normalize_account"),
                },
                "success": lambda payload: payload["pytest"]["returncode"] == 0 and payload["auth"]["contains"]["def normalize_account"] and payload["service"]["contains"]["normalize_account"],
            },
            {
                "name": "cli_migration",
                "repo": Path(manifest["cli_migration_repo"]),
                "prompt": "Migrate this repo off legacy_sum to the new API, preserve behavior, and run the targeted validation.",
                "validator": lambda repo: {
                    "pytest": run_pytest(repo, ["tests/test_consumer.py"], security),
                    "consumer": validate_file_contains(repo, "consumer.py", "sum_numbers"),
                },
                "success": lambda payload: payload["pytest"]["returncode"] == 0 and payload["consumer"]["contains"]["sum_numbers"],
            },
            {
                "name": "cli_repo_overview",
                "repo": Path(manifest["cli_repo_overview_repo"]),
                "prompt": "Create REPO_OVERVIEW.md summarizing the key components in this repo and explicitly mention Python, TypeScript, and Go.",
                "validator": lambda repo: {"overview": validate_file_contains(repo, "REPO_OVERVIEW.md", "Python", "TypeScript", "Go")},
                "success": lambda payload: all(payload["overview"]["contains"].values()),
            },
            {
                "name": "cli_matrix_bugfix",
                "repo": Path(manifest["cli_matrix_bugfix_repo"]),
                "prompt": "Fix the broken feature in this repo and make the relevant tests pass.",
                "validator": lambda repo: {
                    "pytest": run_pytest(repo, ["tests/test_feature_1.py", "tests/test_feature_2.py", "tests/test_feature_3.py", "tests/test_feature_4.py"], security),
                    "file": validate_file_contains(repo, "pkg/feature_4.py", "return value + 4"),
                },
                "success": lambda payload: payload["pytest"]["returncode"] == 0 and payload["file"]["contains"]["return value + 4"],
            },
            {
                "name": "cli_change_runbook",
                "repo": Path(manifest["cli_change_runbook_repo"]),
                "prompt": "Inspect this mixed repo, summarize what changed and what to run, and create CHANGE_RUNBOOK.md with explicit Python, TypeScript, and Go validation commands.",
                "validator": lambda repo: {
                    "languages": validate_file_contains(repo, "CHANGE_RUNBOOK.md", "Python", "TypeScript", "Go"),
                    "commands": validate_file_contains_any(
                        repo,
                        "CHANGE_RUNBOOK.md",
                        {
                            "python": ["pytest -q", "python -m pytest -q", "python -c"],
                            "typescript": ["npm test", "npx ts-node", "tsc --noEmit", "npx tsx"],
                            "go": ["go test ./...", "go run go/cmd/server/main.go", "go build"],
                        },
                    ),
                },
                "success": lambda payload: all(payload["languages"]["contains"].values()) and all(payload["commands"]["contains_any"].values()),
            },
            {
                "name": "cli_big_rollout",
                "repo": Path(manifest["cli_big_rollout_repo"]),
                "prompt": "Roll out the new account normalization naming across this monorepo, preserve behavior, update the docs that still mention the old helper, and run the relevant tests.",
                "validator": lambda repo: {
                    "pytest": run_pytest(repo, ["tests/test_service.py", "tests/test_cli.py"], security),
                    "auth": validate_file_contains(repo, "packages/shared/auth.py", "def normalize_account"),
                    "service": validate_file_contains(repo, "apps/api/service.py", "normalize_account"),
                    "cli": validate_file_contains(repo, "apps/cli/commands.py", "normalize_account"),
                    "docs": validate_file_contains(repo, "docs/auth.md", "normalize_account"),
                },
                "success": lambda payload: payload["pytest"]["returncode"] == 0 and payload["auth"]["contains"]["def normalize_account"] and payload["service"]["contains"]["normalize_account"] and payload["cli"]["contains"]["normalize_account"] and payload["docs"]["contains"]["normalize_account"],
            },
        ]

        cli_summary: dict[str, object] = {}
        for item in cli_tasks:
            cli_result = run_cli(item["prompt"], item["repo"], security)
            validation = item["validator"](item["repo"])
            success = cli_result["returncode"] == 0 and item["success"](validation)
            payload = {"success": success, "cli": cli_result, "validation": validation}
            (output / f"{item['name']}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            cli_summary[item["name"]] = success

        summary = {
            "api_bugfix_success": api_bugfix_success,
            "api_multi_agent_success": api_refactor_success,
            **cli_summary,
            "generic_cli_success_count": sum(1 for key, value in cli_summary.items() if value and key.startswith("cli_")),
            "generic_cli_total": len(cli_summary),
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
