from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..core.repo_index import RepoIndex


class CodebaseIndexer:
    """Compatibility wrapper around the richer RepoIndex intelligence layer."""

    def __init__(self, workspace_path: str = "."):
        self.workspace = Path(workspace_path).resolve()
        self.repo_index = RepoIndex(self.workspace)

    async def build_index(self):
        self.repo_index.build(force=True)

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.repo_index.focus(query, limit=top_k)

    async def symbols(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        return self.repo_index.symbols(query=query, limit=top_k)

    async def impact(self, *changed_files: str, limit: int = 10) -> Dict[str, Any]:
        return self.repo_index.impact_report(changed_files, limit=limit)
