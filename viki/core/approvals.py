from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..config import settings
from ..infrastructure.database import DatabaseManager
from ..infrastructure.security import SecurityScanner


@dataclass
class ApprovalRequest:
    session_id: str
    request_type: str
    subject: str
    reason: str
    risk_score: int
    payload: Dict[str, Any]
    recommended_scope: str = "once"


class ApprovalManager:
    def __init__(self, db: DatabaseManager, security: SecurityScanner):
        self.db = db
        self.security = security
        self._session_grants: Dict[str, Dict[str, set[str]]] = {}

    def _grant_bucket(self, session_id: str, request_type: str) -> set[str]:
        session_state = self._session_grants.setdefault(session_id, {})
        return session_state.setdefault(request_type, set())

    def grant_session_scope(self, session_id: str, request_type: str, subject: str) -> None:
        if not settings.approval_session_grants_enabled:
            return
        self._grant_bucket(session_id, request_type).add(subject)

    def has_session_grant(self, session_id: str, request_type: str, subject: str) -> bool:
        return subject in self._grant_bucket(session_id, request_type)

    def assess_command(self, command: str, session_id: str | None = None) -> tuple[bool, int, str, str]:
        risk = 0
        if session_id and self.has_session_grant(session_id, "command", command):
            return False, 0, "session grant", "session"
        if any(token in command for token in settings.high_risk_command_tokens):
            risk += 60
        if "git push" in command or "gh pr" in command:
            risk += 50
        if "rm " in command:
            risk += 40
        if settings.sandbox_enabled and not any(command.startswith(prefix) for prefix in ["pytest", "python", "ruff", "mypy"]):
            risk += 10
        require = settings.approval_mode == "strict" or risk >= settings.approval_risk_threshold
        scope = "session" if risk < 80 else "once"
        return require, risk, "command risk policy", scope

    def assess_file_operation(self, operation: Dict[str, Any], session_id: str | None = None) -> tuple[bool, int, str, str]:
        risk = 0
        path = operation.get("path", "")
        if session_id and self.has_session_grant(session_id, "file_edit", path):
            return False, 0, "session grant", "session"
        if path.endswith((".env", "secrets.yml", "id_rsa")):
            risk += 80
        if operation.get("mode") == "delete":
            risk += 50
        if settings.skill_dir in path:
            risk += 30
        require = settings.approval_mode == "strict" or risk >= settings.approval_risk_threshold
        scope = "session" if risk < 80 else "once"
        return require, risk, "file risk policy", scope

    async def request(self, request: ApprovalRequest) -> Dict[str, Any]:
        approval_id = await self.db.create_approval(
            session_id=request.session_id,
            request_type=request.request_type,
            subject=request.subject,
            reason=request.reason,
            risk_score=request.risk_score,
            payload={**request.payload, "recommended_scope": request.recommended_scope},
        )
        return {
            "id": approval_id,
            "status": "pending",
            "subject": request.subject,
            "risk_score": request.risk_score,
            "reason": request.reason,
            "recommended_scope": request.recommended_scope,
        }

    async def list_pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.list_approvals(status="pending", limit=limit)

    async def approve(self, approval_id: int, reviewer: str = "local-user", scope: str = "once") -> None:
        approval = await self.db.get_approval(approval_id)
        if approval and scope == "session":
            self.grant_session_scope(approval.get("session_id", ""), approval.get("request_type", ""), approval.get("subject", ""))
        await self.db.resolve_approval(approval_id, status="approved", reviewer=reviewer)

    async def reject(self, approval_id: int, reviewer: str = "local-user") -> None:
        await self.db.resolve_approval(approval_id, status="rejected", reviewer=reviewer)
