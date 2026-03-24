from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import user_config_root

MANAGED_WORKSPACES_DIR = "workspaces"


@dataclass(frozen=True)
class GitHubStatus:
    cli_available: bool
    authenticated: bool
    account: str | None
    protocol: str | None
    scopes: str | None
    error: str | None = None


@dataclass(frozen=True)
class GitHubRepo:
    name_with_owner: str
    url: str
    is_private: bool
    default_branch: str | None
    description: str


def managed_workspace_root() -> Path:
    root = user_config_root() / MANAGED_WORKSPACES_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_gh(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def detect_github_status() -> GitHubStatus:
    if not shutil.which("gh"):
        return GitHubStatus(False, False, None, None, None, error="GitHub CLI (`gh`) is not installed.")
    status = _run_gh(["auth", "status"])
    if status.returncode != 0:
        return GitHubStatus(True, False, None, None, None, error=(status.stderr or status.stdout).strip() or "GitHub CLI is not authenticated.")

    account = None
    protocol = None
    scopes = None
    for raw in (status.stdout + "\n" + status.stderr).splitlines():
        line = raw.strip()
        if "Logged in to github.com account" in line:
            account = line.split("account", 1)[-1].strip().split(" ", 1)[0]
        elif "Git operations protocol:" in line:
            protocol = line.split(":", 1)[-1].strip()
        elif "Token scopes:" in line:
            scopes = line.split(":", 1)[-1].strip().strip("'")
    return GitHubStatus(True, True, account, protocol, scopes)


def list_github_repos(*, owner: str | None = None, limit: int = 20) -> list[GitHubRepo]:
    status = detect_github_status()
    if not status.authenticated:
        return []
    target = owner or status.account
    if not target:
        return []
    result = _run_gh(
        [
            "repo",
            "list",
            target,
            "--limit",
            str(limit),
            "--json",
            "nameWithOwner,url,isPrivate,description,defaultBranchRef",
        ],
        timeout=60,
    )
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    repos: list[GitHubRepo] = []
    for item in payload:
        default_branch = None
        ref = item.get("defaultBranchRef")
        if isinstance(ref, dict):
            default_branch = ref.get("name")
        repos.append(
            GitHubRepo(
                name_with_owner=item.get("nameWithOwner", ""),
                url=item.get("url", ""),
                is_private=bool(item.get("isPrivate", False)),
                default_branch=default_branch,
                description=item.get("description") or "",
            )
        )
    return repos


def clone_github_repo(name_with_owner: str, *, target_root: Path | None = None, branch: str | None = None) -> Path:
    root = (target_root or managed_workspace_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    repo_name = name_with_owner.split("/", 1)[-1]
    target = root / repo_name
    if target.exists():
        return target
    command = ["git", "clone", "--depth", "1"]
    if branch:
        command.extend(["--branch", branch])
    command.extend([f"https://github.com/{name_with_owner}.git", str(target)])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or f"Failed to clone {name_with_owner}.")
    return target
