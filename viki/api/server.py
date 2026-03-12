from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from ..config import settings
from ..core.hive import HiveMind
from ..core.repo_index import RepoIndex
from ..infrastructure.database import DatabaseManager
from ..integrations.telegram import TelegramBotClient, TelegramUpdate
from ..integrations.whatsapp import TwilioWhatsAppClient, WhatsAppInboundMessage, twiml_message
from ..infrastructure.security import SecurityScanner
from ..providers.litellm_provider import LiteLLMProvider
from ..skills.registry import SkillRegistry


class RunRequest(BaseModel):
    prompt: str
    mode: str = "standard"
    workspace: Optional[str] = None


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reviewer: str = "api-user"


class SkillInvokeRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=lambda: ["workspace:read", "workspace:write", "command:run"])
    isolation: Optional[str] = None
    persist_changes: bool = True


class VikiAPIServer:
    def __init__(self, workspace: str | Path = ".", provider: Any | None = None):
        self.workspace = Path(workspace).resolve()
        self.provider = provider or LiteLLMProvider()
        self.db = DatabaseManager(str(self.workspace / settings.workspace_dir / "viki.db"))
        self.telegram = TelegramBotClient()
        self.whatsapp = TwilioWhatsAppClient()
        self.security = SecurityScanner()
        self.app = FastAPI(title="VIKI API", version="4.1.4")
        self.app.state.viki_server = self
        self._register_routes()

    def _protocol_payload(self) -> Dict[str, Any]:
        return {
            "name": "viki-agent-protocol",
            "version": "2026-03-11",
            "run_object": "session",
            "capabilities": {
                "approvals": True,
                "checkpoints": True,
                "resume": True,
                "events": True,
                "skills": True,
                "repo_intelligence": {
                    "search": True,
                    "symbols": True,
                    "impact": True,
                    "context_pack": True,
                },
                "patches": {
                    "diff_preview": True,
                    "patch_bundle": True,
                    "rollback_bundle": True,
                },
                "messaging": {
                    "telegram": self.telegram.enabled,
                    "whatsapp": self.whatsapp.enabled,
                },
            },
        }

    async def _run_hive(self, prompt: str, mode: str = "standard", workspace: str | Path | None = None) -> Dict[str, Any]:
        hive = HiveMind(self.provider, str(Path(workspace or self.workspace).resolve()))
        try:
            await hive.initialize()
            return await hive.process_request(prompt, mode=mode)
        finally:
            await hive.shutdown()

    def _start_hive(self, workspace: str | Path | None = None) -> HiveMind:
        return HiveMind(self.provider, str(Path(workspace or self.workspace).resolve()))

    def _count_failures(self, result: Dict[str, Any]) -> int:
        return len([entry for entry in result.get("commands", []) if entry.get("returncode") not in (0, None)])

    def _format_run_summary(self, result: Dict[str, Any]) -> str:
        lines = [
            f"VIKI session {result.get('session_id', '?')}",
            f"Status: {result.get('status', 'unknown')}",
        ]
        changed = result.get("changed_files") or []
        if changed:
            preview = ", ".join(changed[:6])
            if len(changed) > 6:
                preview += f" (+{len(changed) - 6} more)"
            lines.append(f"Changed: {preview}")
        failures = self._count_failures(result)
        if failures:
            lines.append(f"Failing commands: {failures}")
        approvals = len(result.get("pending_approvals") or [])
        if approvals:
            lines.append(f"Pending approvals: {approvals}")
        created_skills = result.get("created_skills") or []
        if created_skills:
            names = ", ".join(item.get("name", "skill") for item in created_skills[:3])
            lines.append(f"Created skills: {names}")
        return "\n".join(lines)

    async def _integration_status(self, session_id: str) -> str:
        await self.db.initialize()
        session = await self.db.get_session(session_id)
        if not session:
            return f"No session found for {session_id}."
        payload = session.get("result_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = None
        if isinstance(payload, dict) and payload:
            return self._format_run_summary(payload)
        return f"VIKI session {session_id}\nStatus: {session.get('status', 'unknown')}"

    async def _integration_approvals(self) -> str:
        await self.db.initialize()
        items = await self.db.list_approvals(status="pending", limit=10)
        if not items:
            return "No pending approvals."
        lines = ["Pending approvals:"]
        for item in items[:5]:
            lines.append(f"#{item['id']} {item.get('subject', '')} | risk {item.get('risk_score', 0)}")
        return "\n".join(lines)

    async def _latest_session_id(self) -> str | None:
        await self.db.initialize()
        latest = await self.db.get_latest_session()
        return latest.get("id") if latest else None

    async def _integration_sessions(self) -> str:
        await self.db.initialize()
        sessions = await self.db.get_recent_sessions(5)
        if not sessions:
            return "No VIKI sessions found."
        lines = ["Recent sessions:"]
        for item in sessions:
            lines.append(f"- {item['id']} | {item.get('status', '?')} | {(item.get('user_request') or '')[:50]}")
        return "\n".join(lines)

    async def _integration_diff(self, session_id: str | None = None) -> str:
        await self.db.initialize()
        target_id = session_id or await self._latest_session_id()
        if not target_id:
            return "No VIKI sessions found."
        session = await self.db.get_session(target_id)
        if not session:
            return f"No session found for {target_id}."
        payload = session.get("result_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = None
        if not isinstance(payload, dict):
            return f"No diff available for {target_id}."
        previews = payload.get("diff_preview") or []
        if not previews:
            return f"No diff available for {target_id}."
        lines = [f"Diff preview for {target_id}:"]
        for item in previews[:3]:
            lines.append(f"- {item.get('path')} (+{item.get('added', 0)} / -{item.get('removed', 0)})")
        bundles = payload.get("patch_bundles") or []
        if bundles:
            lines.append(f"Patch bundle: {Path(str(bundles[0])).name}")
        return "\n".join(lines)

    async def _integration_patch(self, session_id: str | None = None) -> str:
        await self.db.initialize()
        target_id = session_id or await self._latest_session_id()
        if not target_id:
            return "No VIKI sessions found."
        session = await self.db.get_session(target_id)
        if not session:
            return f"No session found for {target_id}."
        payload = session.get("result_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        payload = payload or {}
        bundles = payload.get("patch_bundles") or []
        if not bundles:
            return f"No patch bundle available for {target_id}."
        rollbacks = []
        for task in payload.get("task_results", []) or []:
            if task.get("rollback_bundle"):
                rollbacks.append(Path(str(task["rollback_bundle"])).name)
        lines = [f"Patch bundle for {target_id}: {Path(str(bundles[0])).name}"]
        if rollbacks:
            lines.append(f"Rollback bundle: {rollbacks[0]}")
        return "\n".join(lines)

    async def _integration_logs(self, session_id: str | None = None) -> str:
        await self.db.initialize()
        target_id = session_id or await self._latest_session_id()
        if not target_id:
            return "No VIKI sessions found."
        session = await self.db.get_session(target_id)
        if not session:
            return f"No session found for {target_id}."
        payload = session.get("result_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        commands = (payload or {}).get("commands") or []
        if not commands:
            return f"No command logs available for {target_id}."
        lines = [f"Latest command results for {target_id}:"]
        for item in commands[-5:]:
            lines.append(f"- rc={item.get('returncode')} | {item.get('command')}")
        return "\n".join(lines)

    async def _integration_symbols(self, query: str) -> str:
        if not query:
            return "Usage: /symbols <query>"
        matches = RepoIndex(self.workspace).symbols(query=query, limit=5)
        if not matches:
            return f"No symbols found for '{query}'."
        lines = [f"Symbols for '{query}':"]
        for item in matches:
            container = f"{item.get('container')}." if item.get("container") else ""
            lines.append(f"- {item.get('path')}:{item.get('line')} {container}{item.get('name')}")
        return "\n".join(lines)

    async def _integration_approval_decision(self, approval_id: int, decision: str) -> str:
        await self.db.initialize()
        approval = await self.db.get_approval(approval_id)
        if not approval:
            return f"Approval #{approval_id} not found."
        if decision == "approve":
            await self.db.resolve_approval(approval_id, status="approved", reviewer="messaging-user")
            return f"Approved #{approval_id}."
        await self.db.resolve_approval(approval_id, status="rejected", reviewer="messaging-user")
        return f"Rejected #{approval_id}."

    def _help_text(self) -> str:
        return "Commands: /help, /latest, /sessions, /status <session_id>, /approvals, /approve <id>, /reject <id>, /diff [session_id], /patch [session_id], /repo [query], /symbols <query>, /logs [session_id]. Any other message starts a VIKI run."

    async def _execute_telegram_run(self, hive: HiveMind, prompt: str, update: TelegramUpdate) -> None:
        try:
            await hive.initialize()
            result = await hive.process_request(prompt, mode="standard")
            self.telegram.send_message(update.chat_id, self._format_run_summary(result), reply_to_message_id=update.message_id)
        except Exception as exc:
            self.telegram.send_message(update.chat_id, f"VIKI run failed: {exc}", reply_to_message_id=update.message_id)
        finally:
            await hive.shutdown()

    async def _execute_whatsapp_run(self, hive: HiveMind, prompt: str, message: WhatsAppInboundMessage) -> None:
        try:
            await hive.initialize()
            result = await hive.process_request(prompt, mode="standard")
            self.whatsapp.send_message(message.sender, self._format_run_summary(result))
        except Exception as exc:
            self.whatsapp.send_message(message.sender, f"VIKI run failed: {exc}")
        finally:
            await hive.shutdown()

    async def _handle_integration_command(self, text: str) -> Optional[str]:
        stripped = text.strip()
        lower = stripped.lower()
        if not stripped:
            return "Send a task for VIKI to run."
        if lower in {"/help", "help"}:
            return self._help_text()
        if lower in {"/latest", "latest"}:
            latest = await self._latest_session_id()
            return f"Latest session: {latest}" if latest else "No VIKI sessions found."
        if lower in {"/sessions", "sessions"}:
            return await self._integration_sessions()
        if lower.startswith("/status "):
            return await self._integration_status(stripped.split(None, 1)[1].strip())
        if lower in {"/approvals", "approvals"}:
            return await self._integration_approvals()
        if lower.startswith("/approve "):
            try:
                approval_id = int(stripped.split(None, 1)[1].strip())
            except Exception:
                return "Usage: /approve <id>"
            return await self._integration_approval_decision(approval_id, "approve")
        if lower.startswith("/reject "):
            try:
                approval_id = int(stripped.split(None, 1)[1].strip())
            except Exception:
                return "Usage: /reject <id>"
            return await self._integration_approval_decision(approval_id, "reject")
        if lower.startswith("/diff"):
            parts = stripped.split(None, 1)
            return await self._integration_diff(parts[1].strip() if len(parts) > 1 else None)
        if lower.startswith("/patch"):
            parts = stripped.split(None, 1)
            return await self._integration_patch(parts[1].strip() if len(parts) > 1 else None)
        if lower.startswith("/logs"):
            parts = stripped.split(None, 1)
            return await self._integration_logs(parts[1].strip() if len(parts) > 1 else None)
        if lower.startswith("/symbols"):
            parts = stripped.split(None, 1)
            return await self._integration_symbols(parts[1].strip() if len(parts) > 1 else "")
        if lower.startswith("/repo") or lower == "repo":
            index = RepoIndex(self.workspace)
            profile = index.profile()
            languages = ", ".join(f"{name}:{count}" for name, count in list((profile.get("languages") or {}).items())[:6]) or "unknown"
            query = stripped.split(None, 1)[1].strip() if len(stripped.split(None, 1)) > 1 else ""
            if query:
                focus = index.focus(query, limit=5)
                symbols = index.symbols(query=query, limit=3)
                focus_lines = [f"- {item['path']} ({item['score']})" for item in focus[:5]] or ["- no matches"]
                symbol_lines = [f"- {item['path']}:{item['line']} {item['name']}" for item in symbols[:3]] or ["- no symbols"]
                return (
                    f"Repo files: {profile.get('file_count', 0)}\n"
                    f"Large repo: {profile.get('large_repo', False)}\n"
                    f"Top languages: {languages}\n"
                    "Matches:\n"
                    + "\n".join(focus_lines)
                    + "\nSymbols:\n"
                    + "\n".join(symbol_lines)
                )
            return f"Repo files: {profile.get('file_count', 0)}\nLarge repo: {profile.get('large_repo', False)}\nTop languages: {languages}"
        return None

    def _register_routes(self) -> None:
        @self.app.get("/healthz")
        async def healthz() -> Dict[str, Any]:
            await self.db.initialize()
            return {
                "ok": True,
                "workspace": str(self.workspace),
                "provider_configured": self.provider.validate_config(),
                "integrations": {
                    "telegram": self.telegram.enabled,
                    "whatsapp": self.whatsapp.enabled,
                },
            }

        @self.app.get("/protocol")
        async def protocol() -> Dict[str, Any]:
            return self._protocol_payload()

        @self.app.get("/repo/profile")
        async def repo_profile() -> Dict[str, Any]:
            index = RepoIndex(self.workspace)
            return {
                "profile": index.profile(),
                "focus": index.focus("repo overview", limit=20),
                "instructions": index.instructions(limit=4),
                "packages": index.package_summaries(limit=8),
                "symbols": index.symbols(limit=12),
            }

        @self.app.get("/repo/search")
        async def repo_search(q: str, limit: int = 10) -> Dict[str, Any]:
            index = RepoIndex(self.workspace)
            return {"query": q, "items": index.focus(q, limit=limit)}

        @self.app.get("/repo/context")
        async def repo_context(q: str = "repo overview", limit: int = 12) -> Dict[str, Any]:
            index = RepoIndex(self.workspace)
            return index.context_pack(q, limit=limit)

        @self.app.get("/repo/symbols")
        async def repo_symbols(q: str = "", path: list[str] = Query(default=[]), limit: int = 20) -> Dict[str, Any]:
            index = RepoIndex(self.workspace)
            return {"query": q, "items": index.symbols(query=q, paths=path, limit=limit)}

        @self.app.get("/repo/impact")
        async def repo_impact(path: list[str] = Query(default=[]), limit: int = 20) -> Dict[str, Any]:
            index = RepoIndex(self.workspace)
            return index.impact_report(path, limit=limit)

        @self.app.get("/integrations")
        async def integrations() -> Dict[str, Any]:
            return {
                "telegram": {
                    "enabled": self.telegram.enabled,
                    "webhook_secret_required": bool(settings.telegram_webhook_secret),
                },
                "whatsapp": {
                    "enabled": self.whatsapp.enabled,
                    "signature_validation": settings.whatsapp_validate_signature,
                },
            }

        @self.app.get("/skills")
        async def skills() -> Dict[str, Any]:
            registry = SkillRegistry(self.workspace)
            return {
                "items": [
                    {
                        "name": record.name,
                        "version": record.version,
                        "permissions": record.permissions or [],
                        "dependencies": record.dependencies or [],
                        "integrity": record.integrity,
                        "signed": record.signed,
                        "isolation": record.isolation,
                    }
                    for record in registry.list_skills()
                ]
            }

        @self.app.post("/skills/{skill_name}/prepare-env")
        async def skill_prepare_env(skill_name: str) -> Dict[str, Any]:
            registry = SkillRegistry(self.workspace)
            if not registry.has(skill_name):
                raise HTTPException(status_code=404, detail="skill not found")
            return registry.prepare_environment(skill_name)

        @self.app.post("/skills/{skill_name}/invoke")
        async def skill_invoke(skill_name: str, payload: SkillInvokeRequest) -> Dict[str, Any]:
            registry = SkillRegistry(self.workspace)
            if not registry.has(skill_name):
                raise HTTPException(status_code=404, detail="skill not found")
            try:
                result = registry.invoke(
                    skill_name,
                    payload.payload,
                    {
                        "workspace": str(self.workspace),
                        "allowed_permissions": payload.permissions,
                        "isolation": payload.isolation,
                        "persist_changes": payload.persist_changes,
                    },
                )
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {"name": skill_name, "result": result}

        @self.app.get("/sessions")
        @self.app.get("/runs")
        async def sessions(limit: int = 20) -> Dict[str, Any]:
            await self.db.initialize()
            return {"items": await self.db.get_recent_sessions(limit=limit), "protocol": self._protocol_payload()}

        @self.app.post("/run")
        @self.app.post("/runs")
        async def run(payload: RunRequest) -> Dict[str, Any]:
            if not self.provider.validate_config():
                raise HTTPException(status_code=400, detail="No provider configured")
            try:
                result = await self._run_hive(payload.prompt, mode=payload.mode, workspace=payload.workspace)
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "VIKI run failed",
                        "error_type": type(exc).__name__,
                        "error": self.security.redact_text(str(exc)),
                    },
                ) from exc
            return {"run": result, "protocol": self._protocol_payload()}

        @self.app.get("/sessions/{session_id}")
        @self.app.get("/runs/{session_id}")
        async def session(session_id: str) -> Dict[str, Any]:
            await self.db.initialize()
            result = await self.db.get_session(session_id)
            if not result:
                raise HTTPException(status_code=404, detail="session not found")
            return {"run": result, "protocol": self._protocol_payload()}

        @self.app.get("/runs/{session_id}/events")
        async def run_events(session_id: str) -> Dict[str, Any]:
            await self.db.initialize()
            session = await self.db.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="session not found")
            checkpoint = await self.db.get_latest_checkpoint(session_id=session_id)
            approvals = [item for item in await self.db.list_approvals(status="pending", limit=100) if item.get("session_id") == session_id]
            events = [{"type": "session", "status": session.get("status"), "timestamp": session.get("updated_at")}]
            if checkpoint:
                events.append({"type": "checkpoint", "timestamp": checkpoint.get("created_at"), "state": checkpoint.get("state_json")})
            for approval in approvals:
                events.append({"type": "approval_pending", "timestamp": approval.get("created_at"), "subject": approval.get("subject")})
            return {"items": events, "protocol": self._protocol_payload()}

        @self.app.get("/runs/{session_id}/diff")
        async def run_diff(session_id: str) -> Dict[str, Any]:
            await self.db.initialize()
            session = await self.db.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="session not found")
            payload = session.get("result_json")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            payload = payload or {}
            return {"items": payload.get("diff_preview", []), "patch_bundles": payload.get("patch_bundles", []), "protocol": self._protocol_payload()}

        @self.app.get("/approvals")
        async def approvals(status: str = "pending") -> Dict[str, Any]:
            await self.db.initialize()
            return {"items": await self.db.list_approvals(status=status, limit=100)}

        @self.app.post("/approvals/{approval_id}")
        async def approval_decision(approval_id: int, payload: ApprovalDecision) -> Dict[str, Any]:
            await self.db.initialize()
            approval = await self.db.get_approval(approval_id)
            if not approval:
                raise HTTPException(status_code=404, detail="approval not found")
            if payload.decision == "approve":
                await self.db.resolve_approval(approval_id, status="approved", reviewer=payload.reviewer)
                status = "approved"
            else:
                await self.db.resolve_approval(approval_id, status="rejected", reviewer=payload.reviewer)
                status = "rejected"
            return {"id": approval_id, "status": status}

        @self.app.get("/sessions/{session_id}/result")
        async def session_result(session_id: str) -> Dict[str, Any]:
            await self.db.initialize()
            result = await self.db.get_session(session_id)
            if not result:
                raise HTTPException(status_code=404, detail="session not found")
            payload = result.get("result_json")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {"raw": payload}
            return {"result": payload or {}, "protocol": self._protocol_payload()}

        @self.app.post("/integrations/telegram/webhook")
        async def telegram_webhook(
            payload: Dict[str, Any],
            background_tasks: BackgroundTasks,
            x_telegram_bot_api_secret_token: str | None = Header(default=None),
        ) -> Dict[str, Any]:
            if not self.telegram.enabled:
                raise HTTPException(status_code=503, detail="telegram integration disabled")
            if not self.telegram.validate_secret(x_telegram_bot_api_secret_token):
                raise HTTPException(status_code=403, detail="telegram webhook secret mismatch")
            update = TelegramUpdate.from_payload(payload)
            if not update or not update.chat_id:
                return {"ok": True, "ignored": True}
            if not self.telegram.is_allowed_chat(update.chat_id):
                self.telegram.send_message(update.chat_id, "Telegram access denied for this chat.", reply_to_message_id=update.message_id)
                return {"ok": True, "accepted": False}
            inline_response = await self._handle_integration_command(update.text)
            if inline_response is not None:
                self.telegram.send_message(update.chat_id, inline_response, reply_to_message_id=update.message_id)
                return {"ok": True, "accepted": False, "command": True}
            if not self.provider.validate_config():
                self.telegram.send_message(update.chat_id, "VIKI provider is not configured.", reply_to_message_id=update.message_id)
                return {"ok": True, "accepted": False}
            hive = self._start_hive()
            self.telegram.send_message(update.chat_id, f"VIKI accepted task. Session {hive.session_id} started.", reply_to_message_id=update.message_id)
            background_tasks.add_task(self._execute_telegram_run, hive, update.text, update)
            return {"ok": True, "accepted": True, "session_id": hive.session_id}

        @self.app.post("/integrations/whatsapp/webhook")
        async def whatsapp_webhook(
            request: Request,
            background_tasks: BackgroundTasks,
            x_twilio_signature: str | None = Header(default=None),
        ) -> Response:
            from urllib.parse import parse_qs

            if not self.whatsapp.enabled:
                raise HTTPException(status_code=503, detail="whatsapp integration disabled")
            raw_body = (await request.body()).decode("utf-8")
            parsed = {key: values[-1] for key, values in parse_qs(raw_body, keep_blank_values=True).items()}
            form_payload = {
                "Body": parsed.get("Body", ""),
                "From": parsed.get("From", ""),
                "ProfileName": parsed.get("ProfileName", ""),
                "MessageSid": parsed.get("MessageSid", ""),
            }
            if not self.whatsapp.validate_signature(str(request.url), form_payload, x_twilio_signature):
                raise HTTPException(status_code=403, detail="whatsapp signature mismatch")
            message = WhatsAppInboundMessage.from_form(form_payload)
            if not message:
                return Response(content=twiml_message("Ignored."), media_type="application/xml")
            if not self.whatsapp.is_allowed_sender(message.sender):
                return Response(content=twiml_message("WhatsApp access denied for this sender."), media_type="application/xml")
            inline_response = await self._handle_integration_command(message.body)
            if inline_response is not None:
                return Response(content=twiml_message(inline_response), media_type="application/xml")
            if not self.provider.validate_config():
                return Response(content=twiml_message("VIKI provider is not configured."), media_type="application/xml")
            hive = self._start_hive()
            background_tasks.add_task(self._execute_whatsapp_run, hive, message.body, message)
            return Response(content=twiml_message(f"VIKI accepted task. Session {hive.session_id} started."), media_type="application/xml")


def create_app(workspace: str | Path = ".", provider: Any | None = None) -> FastAPI:
    return VikiAPIServer(workspace=workspace, provider=provider).app
