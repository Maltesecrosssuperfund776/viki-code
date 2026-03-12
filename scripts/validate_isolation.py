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

from viki.infrastructure.security import ContainerRuntimeProbe, SecurityScanner


def latest_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob("viki_code-*.whl"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not wheels:
        raise FileNotFoundError(f"no wheel found in {dist_dir}")
    return wheels[0]


def windows_to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}{tail}"


def run_wsl(executable: str, distro: str, command: str, env: dict[str, str], timeout: int, security: SecurityScanner) -> dict[str, object]:
    completed = subprocess.run(
        [executable, "-d", distro, "--", "bash", "-lc", command],
        capture_output=True,
        text=False,
        timeout=timeout,
        env=env,
    )
    stdout = completed.stdout.decode("utf-8", errors="ignore") if completed.stdout else ""
    stderr = completed.stderr.decode("utf-8", errors="ignore") if completed.stderr else ""
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": security.redact_text(stdout),
        "stderr": security.redact_text(stderr),
    }


def _forward_wsl_env(env: dict[str, str]) -> dict[str, str]:
    forwarded = [
        name
        for name in [
            "DASHSCOPE_API_KEY",
            "OPENAI_API_BASE",
            "DASHSCOPE_API_BASE",
            "VIKI_REASONING_MODEL",
            "VIKI_CODING_MODEL",
            "VIKI_FAST_MODEL",
        ]
        if env.get(name)
    ]
    if not forwarded:
        return env
    existing = [item for item in env.get("WSLENV", "").split(":") if item]
    for name in forwarded:
        if name not in existing:
            existing.append(name)
    updated = dict(env)
    updated["WSLENV"] = ":".join(existing)
    return updated


def _is_successful_run(commands: list[dict[str, object]], install_strategy: str, content_index: int) -> bool:
    if install_strategy == "venv":
        relevant = commands[:content_index]
        return all(item.get("returncode") == 0 for item in relevant)
    if install_strategy == "user-site-bootstrap":
        expected_ok = [0, 2, 3, 4, 5, 6, 7, 8]
        return all(commands[index].get("returncode") == 0 for index in expected_ok if index < len(commands))
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the strongest feasible isolation runtime for VIKI.")
    parser.add_argument("--workspace", default=".", help="Repository root")
    parser.add_argument("--output", default="LIVE_RUN_RESULTS/isolation_validation", help="Directory for redacted isolation artifacts")
    parser.add_argument("--wheel", default="", help="Optional wheel path; newest dist wheel is used when omitted")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    wheel = Path(args.wheel).resolve() if args.wheel else latest_wheel(workspace / "dist")
    security = SecurityScanner()
    probe = ContainerRuntimeProbe()
    statuses = probe.probe_all()
    serializable_statuses = {name: {"available": item.available, "detail": item.detail, "executable": item.executable, "extra": item.extra} for name, item in statuses.items()}
    (output / "probe.json").write_text(json.dumps(serializable_statuses, indent=2) + "\n", encoding="utf-8")

    best = probe.best_available(statuses)
    if best is None or best.name != "wsl":
        summary = {
            "success": False,
            "blocked": True,
            "best_runtime": best.name if best else None,
            "detail": best.detail if best else "no container-compatible runtime available",
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return

    distro = best.extra.get("distro", "")
    if not distro:
        raise RuntimeError("WSL probe did not return a distro name")

    env = _forward_wsl_env(os.environ.copy())
    wsl_root = "/tmp/viki-isolation-validation"
    wheel_wsl = windows_to_wsl_path(wheel)
    fixture_wsl = windows_to_wsl_path(workspace / "benchmarks" / "public" / "generic_bugfix" / "fixture")
    commands: list[dict[str, object]] = []
    install_strategy = "venv"

    commands.append(run_wsl(best.executable, distro, f"rm -rf {wsl_root} && mkdir -p {wsl_root}", env, 120, security))
    commands.append(run_wsl(best.executable, distro, f"python3 -m venv {wsl_root}/venv", env, 600, security))
    if commands[-1]["returncode"] == 0:
        python_bin = f"{wsl_root}/venv/bin/python"
        pip_bin = f"{python_bin} -m pip"
        viki_bin = f"{wsl_root}/venv/bin/viki"
        commands.append(run_wsl(best.executable, distro, f"{pip_bin} install --upgrade pip", env, 1200, security))
        commands.append(run_wsl(best.executable, distro, f"{pip_bin} install --force-reinstall '{wheel_wsl}' pytest", env, 1800, security))
    else:
        install_strategy = "user-site-bootstrap"
        commands.append(
            run_wsl(
                best.executable,
                distro,
                f"python3 - <<'PY'\nimport urllib.request\nurllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '{wsl_root}/get-pip.py')\nPY",
                env,
                300,
                security,
            )
        )
        commands.append(run_wsl(best.executable, distro, f"python3 {wsl_root}/get-pip.py --user --break-system-packages", env, 1800, security))
        commands.append(run_wsl(best.executable, distro, f"python3 -m pip install --user --break-system-packages --force-reinstall '{wheel_wsl}' pytest", env, 2400, security))
        python_bin = "python3"
        viki_bin = "~/.local/bin/viki"
    commands.append(run_wsl(best.executable, distro, f"cp -R '{fixture_wsl}' {wsl_root}/repo", env, 300, security))
    copy_index = len(commands) - 1
    commands.append(run_wsl(best.executable, distro, f"{viki_bin} version", env, 300, security))
    version_index = len(commands) - 1
    commands.append(run_wsl(best.executable, distro, f"{viki_bin} up {wsl_root}/repo --dry-run", env, 300, security))
    up_index = len(commands) - 1
    commands.append(
        run_wsl(
            best.executable,
            distro,
            f"{viki_bin} run 'Fix the multiply bug in this repo, run the relevant tests, and stop with evidence if confidence is too low.' --path {wsl_root}/repo",
            env,
            2400,
            security,
        )
    )
    live_task_index = len(commands) - 1
    commands.append(run_wsl(best.executable, distro, f"cd {wsl_root}/repo && {python_bin} -m pytest --rootdir . tests/test_calculator.py -q", env, 300, security))
    pytest_index = len(commands) - 1
    commands.append(
        run_wsl(
            best.executable,
            distro,
            f"{python_bin} - <<'PY'\nfrom pathlib import Path\npath = Path('{wsl_root}/repo/app/calculator.py')\ncontent = path.read_text(encoding='utf-8')\nprint('return a * b' in content)\nPY",
            env,
            120,
            security,
        )
    )
    content_index = len(commands) - 1

    summary = {
        "runtime": best.name,
        "distro": distro,
        "wheel": str(wheel),
        "install_strategy": install_strategy,
        "success": _is_successful_run(commands, install_strategy, content_index) and commands[content_index]["stdout"].strip().endswith("True"),
        "copy_ok": commands[copy_index]["returncode"] == 0,
        "version_ok": commands[version_index]["returncode"] == 0,
        "up_ok": commands[up_index]["returncode"] == 0,
        "live_task_ok": commands[live_task_index]["returncode"] == 0,
        "external_pytest_ok": commands[pytest_index]["returncode"] == 0,
        "file_contains_expected_fix": commands[content_index]["stdout"].strip().endswith("True"),
    }

    (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
