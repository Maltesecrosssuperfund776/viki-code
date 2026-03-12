from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass
class DiffPreview:
    path: str
    patch: str
    added: int
    removed: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "patch": self.patch,
            "added": self.added,
            "removed": self.removed,
        }


class DiffManager:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()

    def build_patch(self, source_root: str | Path, files: Iterable[str], max_preview_lines: int = 120) -> list[DiffPreview]:
        source = Path(source_root).resolve()
        previews: list[DiffPreview] = []
        for relative in sorted({str(item) for item in files if item}):
            baseline = self.workspace / relative
            candidate = source / relative
            before = self._read_lines(baseline)
            after = self._read_lines(candidate)
            patch_lines = list(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                    lineterm="",
                )
            )
            if not patch_lines:
                continue
            added = sum(1 for line in patch_lines if line.startswith("+") and not line.startswith("+++"))
            removed = sum(1 for line in patch_lines if line.startswith("-") and not line.startswith("---"))
            patch = "\n".join(patch_lines[:max_preview_lines]).rstrip() + "\n"
            previews.append(DiffPreview(path=relative, patch=patch, added=added, removed=removed))
        return previews

    def export_patch_bundle(self, destination: str | Path, previews: Sequence[DiffPreview]) -> Path:
        output = Path(destination).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(item.patch.rstrip() for item in previews if item.patch.strip()).rstrip() + "\n"
        output.write_text(body if body.strip() else "", encoding="utf-8")
        return output

    def _read_lines(self, path: Path) -> List[str]:
        if not path.exists() or not path.is_file():
            return []
        try:
            return path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return []
