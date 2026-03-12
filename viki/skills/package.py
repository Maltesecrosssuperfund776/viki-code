from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict

import yaml

from ..config import settings
from .environment import SkillEnvironmentManager


class SkillPackageManager:
    def __init__(self, workspace_path: str | Path):
        self.workspace = Path(workspace_path).resolve()
        self.skill_root = self.workspace / settings.skill_dir
        self.skill_root.mkdir(parents=True, exist_ok=True)
        self.environments = SkillEnvironmentManager(self.workspace)

    @staticmethod
    def _hash_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def pack(self, source_dir: str | Path, output_path: str | Path | None = None) -> Dict[str, Any]:
        source = Path(source_dir).resolve()
        manifest_path = source / settings.skill_manifest_name
        code_path = source / "main.py"
        if not manifest_path.exists() or not code_path.exists():
            raise FileNotFoundError("Skill package requires main.py and manifest.yaml")
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        manifest.setdefault("dependencies", [])
        manifest["dependencies"] = self.environments.validate_dependencies(manifest.get("dependencies", []))
        checksum = self._hash_file(code_path)
        manifest["checksum"] = checksum
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        out = Path(output_path).resolve() if output_path else source.with_suffix(".vskill.zip")
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(code_path, arcname="main.py")
            archive.write(manifest_path, arcname=settings.skill_manifest_name)
        return {"archive": str(out), "checksum": checksum, "name": manifest.get("name", source.name)}

    def install(self, archive_path: str | Path) -> Dict[str, Any]:
        archive = Path(archive_path).resolve()
        if not archive.exists():
            raise FileNotFoundError(str(archive))
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with zipfile.ZipFile(archive, "r") as package:
                package.extractall(tmp_root)
            manifest_path = tmp_root / settings.skill_manifest_name
            code_path = tmp_root / "main.py"
            if not manifest_path.exists() or not code_path.exists():
                raise ValueError("Invalid skill archive")
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            manifest.setdefault("dependencies", [])
            manifest["dependencies"] = self.environments.validate_dependencies(manifest.get("dependencies", []))
            checksum = self._hash_file(code_path)
            expected = manifest.get("checksum")
            if expected and expected != checksum:
                raise ValueError("Skill archive checksum mismatch")
            slug = str(manifest.get("name") or archive.stem).strip().lower().replace(" ", "_")
            dest = self.skill_root / slug
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)
            (dest / settings.skill_manifest_name).write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            shutil.copy2(code_path, dest / "main.py")
        return {"name": manifest.get("name", slug), "path": str(dest), "checksum": checksum}
