from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from viki.infrastructure.security import SecurityScanner


def latest_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob("viki_code-*.whl"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not wheels:
        raise FileNotFoundError(f"no wheel found in {dist_dir}")
    return wheels[0]


def copy_fixture(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def run_command(command: list[str], cwd: Path, env: dict[str, str], timeout: int, security: SecurityScanner) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": security.redact_text(completed.stdout),
        "stderr": security.redact_text(completed.stderr),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the built wheel the way a human would install and use it.")
    parser.add_argument("--workspace", default=".", help="Repository root")
    parser.add_argument("--output", default="LIVE_RUN_RESULTS/human_install", help="Directory for redacted install artifacts")
    parser.add_argument("--wheel", default="", help="Optional wheel path; newest dist wheel is used when omitted")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    dist_dir = workspace / "dist"
    wheel = Path(args.wheel).resolve() if args.wheel else latest_wheel(dist_dir)
    fixture_source = workspace / "benchmarks" / "public" / "generic_bugfix" / "fixture"
    task_repo = output / "installed_task_repo"
    copy_fixture(fixture_source, task_repo)

    security = SecurityScanner()
    venv_dir = output / "venv"
    env = os.environ.copy()

    commands: list[dict[str, object]] = []
    commands.append(run_command([sys.executable, "-m", "venv", str(venv_dir)], workspace, env, 600, security))

    scripts_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    python_bin = scripts_dir / ("python.exe" if os.name == "nt" else "python")
    pip_bin = scripts_dir / ("pip.exe" if os.name == "nt" else "pip")
    viki_bin = scripts_dir / ("viki.exe" if os.name == "nt" else "viki")

    commands.append(run_command([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], workspace, env, 1200, security))
    commands.append(run_command([str(pip_bin), "install", str(wheel), "pytest"], workspace, env, 1800, security))
    commands.append(run_command([str(viki_bin), "--help"], workspace, env, 300, security))
    commands.append(run_command([str(viki_bin), "version"], workspace, env, 300, security))
    commands.append(run_command([str(viki_bin), "doctor", str(task_repo)], workspace, env, 300, security))
    commands.append(run_command([str(viki_bin), "up", str(task_repo), "--dry-run"], workspace, env, 300, security))
    commands.append(
        run_command(
            [
                str(viki_bin),
                "run",
                "Fix the multiply bug in this repo, run the relevant tests, and stop with evidence if confidence is too low.",
                "--path",
                str(task_repo),
            ],
            workspace,
            env,
            2400,
            security,
        )
    )
    commands.append(
        run_command(
            [str(python_bin), "-m", "pytest", "--rootdir", ".", "tests/test_calculator.py", "-q"],
            task_repo,
            env,
            300,
            security,
        )
    )
    commands.append(run_command([str(pip_bin), "install", "--upgrade", str(wheel)], workspace, env, 1800, security))
    commands.append(run_command([str(python_bin), "-m", "pip", "uninstall", "-y", "viki-code"], workspace, env, 600, security))
    commands.append(run_command([str(python_bin), "-m", "pip", "show", "viki-code"], workspace, env, 300, security))

    calculator = task_repo / "app" / "calculator.py"
    file_contains = calculator.exists() and "return a * b" in calculator.read_text(encoding="utf-8", errors="ignore")
    summary = {
        "wheel": str(wheel),
        "installed_entrypoint": str(viki_bin),
        "task_repo": str(task_repo),
        "success": all(item["returncode"] == 0 for item in commands[:-1]) and commands[-1]["returncode"] != 0 and file_contains,
        "help_ok": commands[3]["returncode"] == 0,
        "version_ok": commands[4]["returncode"] == 0,
        "doctor_ok": commands[5]["returncode"] == 0,
        "dry_run_ok": commands[6]["returncode"] == 0,
        "live_task_ok": commands[7]["returncode"] == 0,
        "external_pytest_ok": commands[8]["returncode"] == 0,
        "update_ok": commands[9]["returncode"] == 0,
        "uninstall_ok": commands[10]["returncode"] == 0 and commands[11]["returncode"] != 0,
        "file_contains_expected_fix": file_contains,
    }

    (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
