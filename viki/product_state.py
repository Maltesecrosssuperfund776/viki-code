from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import user_config_root

STATE_FILENAME = "state.json"
MAX_RECENT_WORKSPACES = 8


@dataclass(frozen=True)
class ProductState:
    active_workspace: str | None = None
    recent_workspaces: tuple[str, ...] = ()


def state_path() -> Path:
    return user_config_root() / STATE_FILENAME


def load_product_state() -> ProductState:
    path = state_path()
    if not path.exists():
        return ProductState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ProductState()
    active_workspace = payload.get("active_workspace")
    recent_workspaces = tuple(
        item for item in payload.get("recent_workspaces", []) if isinstance(item, str) and item.strip()
    )
    return ProductState(active_workspace=active_workspace, recent_workspaces=recent_workspaces)


def save_product_state(state: ProductState) -> Path:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_workspace": state.active_workspace,
        "recent_workspaces": list(state.recent_workspaces[:MAX_RECENT_WORKSPACES]),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def remember_workspace(path: Path) -> ProductState:
    normalized = str(path.resolve())
    current = load_product_state()
    recent = [item for item in current.recent_workspaces if item != normalized]
    recent.insert(0, normalized)
    state = ProductState(
        active_workspace=normalized,
        recent_workspaces=tuple(recent[:MAX_RECENT_WORKSPACES]),
    )
    save_product_state(state)
    return state


def set_active_workspace(path: Path) -> ProductState:
    return remember_workspace(path)


def active_workspace_path() -> Path | None:
    state = load_product_state()
    if not state.active_workspace:
        return None
    candidate = Path(state.active_workspace).expanduser()
    return candidate if candidate.exists() else None


def recent_workspace_paths() -> list[Path]:
    state = load_product_state()
    items: list[Path] = []
    for entry in state.recent_workspaces:
        candidate = Path(entry).expanduser()
        if candidate.exists():
            items.append(candidate)
    return items
