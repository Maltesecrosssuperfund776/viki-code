from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from ..tools.diffing import DiffManager


@dataclass
class IsolatedWorkspace:
    root: Path
    mode: str


class WorktreeManager:
    def __init__(self, workspace: str | Path, runs_dir: str | Path):
        self.workspace = Path(workspace).resolve()
        self.runs_dir = Path(runs_dir).resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._active: List[IsolatedWorkspace] = []
        self.diff_manager = DiffManager(self.workspace)

    def create(self, label: str) -> IsolatedWorkspace:
        if (self.workspace / ".git").exists() and shutil.which("git"):
            root = self.runs_dir / label
            if root.exists():
                shutil.rmtree(root, ignore_errors=True)
            subprocess.run(["git", "worktree", "add", "--detach", str(root), "HEAD"], cwd=self.workspace, check=False, capture_output=True)
            if root.exists():
                ws = IsolatedWorkspace(root=root, mode="git-worktree")
                self._active.append(ws)
                return ws
        temp_root = Path(tempfile.mkdtemp(prefix=f"viki-{label}-", dir=str(self.runs_dir)))
        self._copy_workspace(self.workspace, temp_root)
        ws = IsolatedWorkspace(root=temp_root, mode="shadow-copy")
        self._active.append(ws)
        return ws

    def _copy_workspace(self, source: Path, dest: Path) -> None:
        ignored = {".git", ".viki-workspace", "node_modules", "__pycache__", ".pytest_cache", "dist", "build"}
        for root, dirs, files in os.walk(source):
            rel_root = Path(root).relative_to(source)
            if any(part in ignored for part in rel_root.parts):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in ignored]
            target_root = dest / rel_root
            target_root.mkdir(parents=True, exist_ok=True)
            for file_name in files:
                src = Path(root) / file_name
                rel = src.relative_to(source)
                if any(part in ignored for part in rel.parts):
                    continue
                shutil.copy2(src, dest / rel)


    def sync_back(self, source_root: Path, files: Iterable[str]) -> Dict[str, List[str]]:
        copied: List[str] = []
        deleted: List[str] = []
        for relative in sorted(set(str(item) for item in files if item)):
            src = (Path(source_root) / relative).resolve()
            dst = (self.workspace / relative).resolve()
            if self.workspace not in dst.parents and dst != self.workspace:
                raise ValueError(f"Path escapes workspace during sync: {relative}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists() and src.is_file():
                tmp = dst.with_suffix(dst.suffix + ".viki-tmp")
                shutil.copy2(src, tmp)
                os.replace(tmp, dst)
                copied.append(relative.replace("\\", "/"))
            elif dst.exists():
                dst.unlink()
                deleted.append(relative.replace("\\", "/"))
        return {"copied": copied, "deleted": deleted}


    def diff_preview(self, source_root: Path, files: Iterable[str], max_preview_lines: int = 120) -> List[Dict[str, object]]:
        return [item.to_dict() for item in self.diff_manager.build_patch(source_root, files, max_preview_lines=max_preview_lines)]

    def export_patch_bundle(self, source_root: Path, files: Iterable[str], destination: Path) -> Path:
        previews = self.diff_manager.build_patch(source_root, files)
        return self.diff_manager.export_patch_bundle(destination, previews)

    def export_rollback_bundle(self, source_root: Path, files: Iterable[str], destination: Path) -> Path:
        previews = DiffManager(source_root).build_patch(self.workspace, files)
        return self.diff_manager.export_patch_bundle(destination, previews)

    def stage_files(self, files: Iterable[str], destination: Path) -> None:
        for relative in files:
            src = self.workspace / relative
            if not src.exists():
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    def cleanup(self) -> None:
        for ws in reversed(self._active):
            if ws.mode == "git-worktree":
                subprocess.run(["git", "worktree", "remove", "--force", str(ws.root)], cwd=self.workspace, check=False, capture_output=True)
            shutil.rmtree(ws.root, ignore_errors=True)
        self._active.clear()
