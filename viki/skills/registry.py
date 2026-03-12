from __future__ import annotations

import hashlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

from ..config import settings
from .environment import SkillEnvironmentManager
from .policy import SkillPermissionPolicy
from .runner import IsolatedSkillRunner


@dataclass
class SkillRecord:
    name: str
    description: str
    source: str
    func: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    version: str = "0.1.0"
    permissions: List[str] | None = None
    dependencies: List[str] | None = None
    checksum: str | None = None
    integrity: str = "unverified"
    signed: bool = False
    isolation: str = "per_run"


class SkillRegistry:
    def __init__(self, workspace_path: str | Path):
        self.workspace = Path(workspace_path).resolve()
        self.skill_root = self.workspace / settings.skill_dir
        self.skill_root.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, SkillRecord] = {}
        self.policy = SkillPermissionPolicy()
        self.environments = SkillEnvironmentManager(self.workspace)
        self.runner = IsolatedSkillRunner(self.workspace)
        self._load_builtins()
        self.load_user_skills()

    def _load_builtins(self):
        from .builtin import BUILTIN_SKILLS

        for item in BUILTIN_SKILLS:
            self._skills[item["name"]] = SkillRecord(
                name=item["name"],
                description=item["description"],
                source="builtin",
                func=item["func"],
                version="1.0.0",
                permissions=list(item.get("permissions", [])),
                dependencies=[],
                checksum="builtin",
                integrity="builtin",
                signed=True,
                isolation="in_process",
            )

    def _hash_file(self, path: Path) -> str:
        normalized = path.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n").encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    def _load_module(self, path: Path, manifest: Dict[str, Any] | None = None):
        module_name = f"viki_user_skill_{path.stem}_{abs(hash(str(path)))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        name = (manifest or {}).get("name") or getattr(module, "SKILL_NAME", path.stem)
        description = (manifest or {}).get("description") or getattr(module, "SKILL_DESCRIPTION", name)
        version = (manifest or {}).get("version", "0.1.0")
        permissions = list((manifest or {}).get("permissions", []))
        dependencies = self.environments.validate_dependencies((manifest or {}).get("dependencies", []))
        checksum = self._hash_file(path)
        expected_checksum = (manifest or {}).get("checksum")
        integrity = "verified" if expected_checksum and expected_checksum == checksum else "unverified"
        signed = bool((manifest or {}).get("signature") or (manifest or {}).get("signed"))
        isolation = str((manifest or {}).get("isolation", "per_run"))
        run = getattr(module, "run", None)
        if callable(run):
            self._skills[name] = SkillRecord(
                name=name,
                description=description,
                source=str(path),
                func=run,
                version=version,
                permissions=permissions,
                dependencies=dependencies,
                checksum=checksum,
                integrity=integrity,
                signed=signed,
                isolation=isolation,
            )

    def load_user_skills(self):
        for path in sorted(self.skill_root.glob("*.py")):
            self._load_module(path)
        for skill_dir in sorted(p for p in self.skill_root.iterdir() if p.is_dir()):
            manifest_path = skill_dir / settings.skill_manifest_name
            code_path = skill_dir / "main.py"
            if not manifest_path.exists() or not code_path.exists():
                continue
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            self._load_module(code_path, manifest=manifest)

    def list_skills(self) -> List[SkillRecord]:
        return sorted(self._skills.values(), key=lambda item: item.name)

    def has(self, name: str) -> bool:
        return name in self._skills

    def get(self, name: str) -> SkillRecord | None:
        return self._skills.get(name)

    def prepare_environment(self, name: str, upgrade: bool = False) -> dict[str, Any]:
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(f"skill not found: {name}")
        python_path = self.environments.prepare(skill.name, skill.checksum, skill.dependencies, upgrade=upgrade)
        description = self.environments.describe(skill.name, skill.checksum)
        description["python"] = str(python_path)
        return description

    def invoke(self, name: str, payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(f"skill not found: {name}")
        decision = self.policy.evaluate(skill.permissions, context)
        if not decision.allowed:
            missing = ", ".join(decision.missing)
            raise PermissionError(f"skill '{name}' missing permissions: {missing}")
        runtime = dict(context)
        runtime.setdefault("workspace", str(self.workspace))
        runtime.setdefault("allowed_permissions", decision.granted)
        runtime.setdefault("allowed_command_prefixes", list(settings.allowed_command_prefixes))
        runtime.setdefault("isolation", skill.isolation)
        return self.runner.invoke(skill, payload, runtime)
