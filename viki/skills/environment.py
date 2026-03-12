from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any, Iterable

from ..config import settings

PINNED_REQUIREMENT = re.compile(r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+\-]+$")


class SkillDependencyError(ValueError):
    pass


class SkillEnvironmentManager:
    def __init__(self, workspace_path: str | Path):
        self.workspace = Path(workspace_path).resolve()
        self.env_root = self.workspace / settings.skill_env_dir
        self.env_root.mkdir(parents=True, exist_ok=True)

    def slug(self, name: str) -> str:
        return re.sub(r"[^a-z0-9_.-]+", "_", name.lower()).strip("_") or "skill"

    def env_dir(self, skill_name: str, checksum: str | None = None) -> Path:
        suffix = checksum[:12] if checksum else "default"
        return self.env_root / self.slug(skill_name) / suffix

    def python_path(self, env_dir: Path) -> Path:
        return env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def validate_dependency(self, spec: str) -> str:
        item = str(spec or "").strip()
        if not item:
            raise SkillDependencyError("empty dependency spec")
        if PINNED_REQUIREMENT.match(item):
            return item
        candidate = Path(item)
        if candidate.suffix == ".whl":
            if not candidate.is_absolute():
                candidate = (self.workspace / candidate).resolve()
            if not candidate.exists():
                raise SkillDependencyError(f"local wheel not found: {item}")
            return str(candidate)
        raise SkillDependencyError(
            f"dependency must be pinned with == or reference a local wheel: {item}"
        )

    def validate_dependencies(self, dependencies: Iterable[str] | None) -> list[str]:
        return [self.validate_dependency(item) for item in (dependencies or [])]

    def _meta_path(self, env_dir: Path) -> Path:
        return env_dir / "skill_env.json"

    def is_ready(self, skill_name: str, checksum: str | None, dependencies: Iterable[str] | None) -> bool:
        env_dir = self.env_dir(skill_name, checksum)
        meta = self._meta_path(env_dir)
        py = self.python_path(env_dir)
        if not py.exists() or not meta.exists():
            return False
        try:
            payload = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            return False
        return payload.get("dependencies") == list(dependencies or [])

    def prepare(self, skill_name: str, checksum: str | None, dependencies: Iterable[str] | None, upgrade: bool = False) -> Path:
        pinned = self.validate_dependencies(dependencies)
        env_dir = self.env_dir(skill_name, checksum)
        py = self.python_path(env_dir)
        if upgrade and env_dir.exists():
            shutil.rmtree(env_dir)
        if not env_dir.exists():
            try:
                builder = venv.EnvBuilder(with_pip=True, clear=False, symlinks=os.name != "nt")
                builder.create(env_dir)
            except Exception:
                env_dir.mkdir(parents=True, exist_ok=True)
                py = Path(sys.executable)
        if pinned:
            cmd = [str(py), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *pinned]
            subprocess.run(
                cmd,
                cwd=str(self.workspace),
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                    "PIP_NO_INPUT": "1",
                    "PYTHONNOUSERSITE": "1",
                },
                check=True,
                capture_output=True,
                text=True,
            )
        self._meta_path(env_dir).write_text(
            json.dumps(
                {
                    "skill_name": skill_name,
                    "checksum": checksum,
                    "dependencies": pinned,
                    "python": str(py),
                    "base_python": sys.executable,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return py

    def python_for_skill(self, skill_name: str, checksum: str | None, dependencies: Iterable[str] | None) -> Path:
        if not dependencies:
            return Path(sys.executable)
        if not self.is_ready(skill_name, checksum, dependencies):
            return self.prepare(skill_name, checksum, dependencies)
        return self.python_path(self.env_dir(skill_name, checksum))

    def describe(self, skill_name: str, checksum: str | None) -> dict[str, Any]:
        env_dir = self.env_dir(skill_name, checksum)
        meta = self._meta_path(env_dir)
        payload: dict[str, Any] = {"path": str(env_dir), "ready": False}
        if meta.exists():
            try:
                payload.update(json.loads(meta.read_text(encoding="utf-8")))
                payload["ready"] = True
            except Exception:
                payload["ready"] = False
        payload["python"] = str(self.python_path(env_dir))
        return payload
