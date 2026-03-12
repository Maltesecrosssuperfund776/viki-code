from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .._log import structlog

from ..config import settings

logger = structlog.get_logger()

try:
    import docker  # type: ignore
except Exception:
    docker = None


@dataclass
class SandboxExecutionProfile:
    command: str
    workspace: str
    timeout: int = 120
    network_enabled: bool = False
    memory_limit: str = "2g"
    nano_cpus: int = 2_000_000_000
    pids_limit: int = 256
    environment: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class ContainerRuntimeStatus:
    name: str
    available: bool
    detail: str
    executable: str = ""
    extra: Dict[str, str] = field(default_factory=dict)


class SecurityScanner:
    def __init__(self):
        self.forbidden_patterns = [re.compile(p) for p in settings.forbidden_modules]
        self.secret_patterns = [re.compile(r"(" + re.escape(p) + r"[a-zA-Z0-9_\-]+)") for p in settings.secret_patterns]
        self.risky_command_patterns = [
            re.compile(r"(^|\s)rm\s+-rf\s+/((\s)|$)"),
            re.compile(r"curl\s+.*\|\s*(sh|bash)"),
            re.compile(r"wget\s+.*\|\s*(sh|bash)"),
            re.compile(r"(^|\s)chmod\s+777"),
        ]

    def scan_code(self, code: str, filename: str = "dynamic.py") -> Tuple[bool, List[str]]:
        violations: List[str] = []
        for pattern in self.forbidden_patterns:
            if pattern.search(code):
                violations.append(f"FORBIDDEN_PATTERN:{pattern.pattern}")
        for pattern in self.secret_patterns:
            matches = pattern.findall(code)
            if matches:
                violations.append(f"POTENTIAL_SECRET:{matches[0][:20]}...")
        try:
            import bandit
            from bandit.core import config as bandit_config
            from bandit.core import manager as bandit_manager

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as handle:
                handle.write(code)
                temp_path = handle.name
            conf = bandit_config.BanditConfig()
            manager = bandit_manager.BanditManager(conf, agg_type="file")
            manager.discover_files([temp_path])
            manager.run_tests()
            for issue in manager.get_issue_list():
                violations.append(f"BANDIT:{issue.severity}:{issue.text}")
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("bandit scan failed", error=str(exc), filename=filename)
        finally:
            if "temp_path" in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
        return len(violations) == 0, violations

    def scan_file_changes(self, changed_files: Dict[str, str]) -> Tuple[bool, Dict[str, List[str]]]:
        issues: Dict[str, List[str]] = {}
        for path, content in changed_files.items():
            safe, violations = self.scan_code(content, path)
            if not safe:
                issues[path] = violations
        return len(issues) == 0, issues

    def validate_command(self, command: str) -> Tuple[bool, str]:
        if not command.strip():
            return False, "empty command"
        try:
            tokens = shlex.split(command, posix=os.name != "nt")
        except ValueError:
            return False, "malformed shell command"
        if not tokens:
            return False, "empty tokenized command"
        prefix = tokens[0]
        if prefix not in settings.allowed_command_prefixes:
            return False, f"command prefix '{prefix}' not allowed"
        for pattern in self.risky_command_patterns:
            if pattern.search(command):
                return False, f"command blocked by security pattern: {pattern.pattern}"
        return True, "ok"

    def redact_text(self, text: str) -> str:
        redacted = text
        for pattern in self.secret_patterns:
            redacted = pattern.sub("[REDACTED_SECRET]", redacted)
        return redacted


class SecretBroker:
    def __init__(self):
        self.prefixes = tuple(settings.secret_patterns)

    def export(self, names: List[str]) -> Dict[str, str]:
        resolved = {}
        for name in names:
            value = os.getenv(name)
            if value:
                resolved[name] = value
        return resolved

    def redact_mapping(self, payload: Dict[str, str]) -> Dict[str, str]:
        return {key: ("***" if value else "") for key, value in payload.items()}


class ContainerRuntimeProbe:
    def _run(self, args: List[str], timeout: int = 15) -> tuple[bool, str]:
        try:
            completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
        except FileNotFoundError:
            return False, "command not found"
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip() or f"exit {exc.returncode}"
            return False, detail
        except Exception as exc:
            return False, str(exc)
        return True, (completed.stdout or completed.stderr or "").strip()

    def probe_docker(self) -> ContainerRuntimeStatus:
        executable = shutil.which("docker") or ""
        if not executable:
            return ContainerRuntimeStatus("docker", False, "docker command not found")
        ok, detail = self._run([executable, "info", "--format", "{{json .ServerVersion}}"])
        return ContainerRuntimeStatus("docker", ok, detail or "docker available", executable=executable)

    def probe_podman(self) -> ContainerRuntimeStatus:
        executable = shutil.which("podman") or ""
        if not executable:
            return ContainerRuntimeStatus("podman", False, "podman command not found")
        ok, detail = self._run([executable, "info", "--format", "json"])
        return ContainerRuntimeStatus("podman", ok, detail or "podman available", executable=executable)

    def probe_wsl(self) -> ContainerRuntimeStatus:
        executable = shutil.which("wsl.exe") or shutil.which("wsl") or ""
        if not executable:
            return ContainerRuntimeStatus("wsl", False, "wsl command not found")
        ok, detail = self._run([executable, "-l", "-q"])
        if not ok:
            return ContainerRuntimeStatus("wsl", False, detail, executable=executable)
        distros = [item.replace("\x00", "").strip() for item in detail.splitlines() if item.replace("\x00", "").strip()]
        if not distros:
            return ContainerRuntimeStatus("wsl", False, "no WSL distributions installed", executable=executable)
        distro = distros[0]
        py_ok, py_detail = self._run([executable, "-d", distro, "--", "bash", "-lc", "python3 --version"], timeout=20)
        extra = {"distro": distro}
        if py_ok:
            extra["python"] = py_detail
            return ContainerRuntimeStatus("wsl", True, py_detail, executable=executable, extra=extra)
        return ContainerRuntimeStatus("wsl", False, f"{distro}: {py_detail}", executable=executable, extra=extra)

    def probe_all(self) -> Dict[str, ContainerRuntimeStatus]:
        return {
            "docker": self.probe_docker(),
            "podman": self.probe_podman(),
            "wsl": self.probe_wsl(),
        }

    def best_available(self, statuses: Dict[str, ContainerRuntimeStatus] | None = None) -> ContainerRuntimeStatus | None:
        available = statuses or self.probe_all()
        for name in ("docker", "podman", "wsl"):
            status = available[name]
            if status.available:
                return status
        return None


class DockerSandbox:
    def __init__(self):
        self.image = settings.docker_image
        self.client = None
        if docker is None:
            return
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as exc:
            logger.warning("docker unavailable", error=str(exc))
            self.client = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def build_profile(
        self,
        workspace: str,
        command: str,
        timeout: int = 120,
        network_enabled: bool = False,
        environment: Dict[str, str] | None = None,
        labels: Dict[str, str] | None = None,
    ) -> SandboxExecutionProfile:
        return SandboxExecutionProfile(
            workspace=workspace,
            command=command,
            timeout=timeout,
            network_enabled=network_enabled,
            memory_limit=settings.sandbox_memory_limit,
            nano_cpus=settings.sandbox_nano_cpus,
            pids_limit=settings.sandbox_pids_limit,
            environment=dict(environment or {}),
            labels={"app": "viki", **(labels or {})},
        )

    def run_command(self, workspace: str, command: str, timeout: int = 120, network_enabled: bool = False, environment: Dict[str, str] | None = None, labels: Dict[str, str] | None = None) -> Dict[str, str | int | bool | dict]:
        if not self.client:
            raise RuntimeError("docker sandbox unavailable")
        profile = self.build_profile(workspace, command, timeout=timeout, network_enabled=network_enabled, environment=environment, labels=labels)
        container = self.client.containers.run(
            self.image,
            ["/bin/bash", "-lc", profile.command],
            working_dir="/workspace",
            volumes={str(profile.workspace): {"bind": "/workspace", "mode": "rw"}},
            network_disabled=not profile.network_enabled,
            environment=profile.environment,
            mem_limit=profile.memory_limit,
            nano_cpus=profile.nano_cpus,
            pids_limit=profile.pids_limit,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            detach=True,
            stdout=True,
            stderr=True,
            labels=profile.labels,
        )
        try:
            result = container.wait(timeout=profile.timeout)
            logs = container.logs(stdout=True, stderr=False).decode("utf-8", errors="ignore")
            errors = container.logs(stdout=False, stderr=True).decode("utf-8", errors="ignore")
            status_code = int(result.get("StatusCode", 1)) if isinstance(result, dict) else int(result)
            return {
                "returncode": status_code,
                "output": logs,
                "error": errors,
                "runtime": "docker",
                "sandboxed": True,
                "profile": {
                    "network_enabled": profile.network_enabled,
                    "memory_limit": profile.memory_limit,
                    "nano_cpus": profile.nano_cpus,
                    "pids_limit": profile.pids_limit,
                },
            }
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass

    def cleanup(self):
        if not self.client:
            return
        try:
            self.client.containers.prune()
        except Exception:
            pass
