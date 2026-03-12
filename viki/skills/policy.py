from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


DEFAULT_ALLOWED_PERMISSIONS = ["workspace:read", "workspace:write", "command:run"]


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    missing: list[str]
    granted: list[str]


class SkillPermissionPolicy:
    def __init__(self, default_permissions: Sequence[str] | None = None):
        self.default_permissions = list(default_permissions or DEFAULT_ALLOWED_PERMISSIONS)

    def granted_permissions(self, context: dict) -> list[str]:
        granted = context.get("allowed_permissions") or context.get("permissions")
        if not granted:
            return list(self.default_permissions)
        return [str(item).strip() for item in granted if str(item).strip()]

    @staticmethod
    def _matches(required: str, granted: str) -> bool:
        if granted in {"*", required}:
            return True
        if granted.endswith(":*"):
            return required.startswith(granted[:-1])
        return False

    def evaluate(self, required_permissions: Iterable[str] | None, context: dict) -> PermissionDecision:
        required = [str(item).strip() for item in (required_permissions or []) if str(item).strip()]
        granted = self.granted_permissions(context)
        missing = [perm for perm in required if not any(self._matches(perm, item) for item in granted)]
        return PermissionDecision(allowed=not missing, missing=missing, granted=granted)
