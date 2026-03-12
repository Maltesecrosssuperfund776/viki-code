from __future__ import annotations

from typing import Any, Dict, List


def _read_file(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    executor = context["executor"]
    path = executor.resolve_path(payload["path"])
    return {"path": payload["path"], "content": path.read_text(encoding="utf-8", errors="ignore")}


def _write_file(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    executor = context["executor"]
    changed = executor.apply_file_operations([{"mode": "write", "path": payload["path"], "content": payload.get("content", "")}])
    return {"changed_files": changed}


def _append_file(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    executor = context["executor"]
    changed = executor.apply_file_operations([{"mode": "append", "path": payload["path"], "content": payload.get("content", "")}])
    return {"changed_files": changed}


def _search_files(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    executor = context["executor"]
    return {"results": executor.search_files(payload["query"], int(payload.get("limit", 10)))}


def _run_command(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    executor = context["executor"]
    return executor.run_command(payload["command"], int(payload.get("timeout", 120)))


BUILTIN_SKILLS: List[Dict[str, Any]] = [
    {"name": "read_file", "description": "Read a file from the workspace", "func": _read_file, "permissions": ["workspace:read"]},
    {"name": "write_file", "description": "Write a file into the workspace", "func": _write_file, "permissions": ["workspace:write"]},
    {"name": "append_file", "description": "Append content to a workspace file", "func": _append_file, "permissions": ["workspace:write"]},
    {"name": "search_files", "description": "Search workspace files by keyword", "func": _search_files, "permissions": ["workspace:read"]},
    {"name": "run_command", "description": "Execute an allowed build or test command", "func": _run_command, "permissions": ["command:run"]},
]
