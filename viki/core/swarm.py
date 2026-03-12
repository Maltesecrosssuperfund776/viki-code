from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from .agent import Agent, AgentStatus
from ..infrastructure.database import DatabaseManager
from ..infrastructure.observability import MetricsCollector
from ..infrastructure.security import SecurityScanner


class SwarmType(Enum):
    PLANNING = "planning"
    CODING = "coding"
    SECURITY = "security"
    TESTING = "testing"
    REFACTORING = "refactoring"
    DEBUGGING = "debugging"


@dataclass
class SwarmConfig:
    max_retries: int = 3
    timeout_seconds: int = 180
    enable_security_scan: bool = True
    checkpoint_interval: int = 30


class SwarmPod:
    def __init__(
        self,
        swarm_type: SwarmType,
        objective: str,
        provider: Any,
        db: DatabaseManager,
        metrics: MetricsCollector,
        security: SecurityScanner,
        parent_swarm: Optional["SwarmPod"] = None,
        depth: int = 0,
        config: Optional[SwarmConfig] = None,
        model_hint: Optional[str] = None,
    ):
        self.swarm_type = swarm_type
        self.objective = objective
        self.provider = provider
        self.db = db
        self.metrics = metrics
        self.security = security
        self.parent = parent_swarm
        self.depth = depth
        self.config = config or SwarmConfig()
        self.id = f"{swarm_type.value}-{depth}-{int(time.time() * 1000)}"
        self.agents: List[Agent] = []
        self.results: Dict[str, Any] = {}
        self.status = "initializing"
        self.session_id: Optional[str] = None
        self._cancelled = False
        self.model_hint = model_hint

    def _roles(self) -> List[str]:
        return {
            SwarmType.PLANNING: ["architect", "planner", "validator"],
            SwarmType.CODING: ["coder", "reviewer", "integrator"],
            SwarmType.SECURITY: ["auditor", "security_analyst"],
            SwarmType.TESTING: ["test_writer", "test_runner"],
            SwarmType.REFACTORING: ["refactorer", "validator"],
            SwarmType.DEBUGGING: ["debugger", "root_cause_analyst"],
        }[self.swarm_type]

    async def initialize_agents(self, session_id: Optional[str] = None):
        if self.agents:
            return
        self.session_id = session_id or self.session_id
        self.agents = [Agent(role=role) for role in self._roles()]
        await self.db.create_swarm({
            "id": self.id,
            "session_id": self.session_id or "pending",
            "parent_id": self.parent.id if self.parent else None,
            "type": self.swarm_type.value,
            "status": "initialized",
            "depth": self.depth,
            "objective": self.objective,
        })
        self.status = "ready"

    def _model_alias(self) -> str:
        if self.model_hint:
            return self.model_hint
        if self.swarm_type == SwarmType.PLANNING:
            return "reasoning"
        if self.swarm_type in {SwarmType.CODING, SwarmType.REFACTORING, SwarmType.DEBUGGING}:
            return "coding"
        return "fast"

    def _extract_json(self, text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.S)
        if fence_match:
            cleaned = fence_match.group(1)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end >= start:
            cleaned = cleaned[start:end + 1]
        return json.loads(cleaned)

    def _swarm_rules(self) -> str:
        if self.swarm_type == SwarmType.PLANNING:
            return (
                "Plan only executable work. Avoid pure read-only or inspection-only tasks unless the entire user request is analysis only. "
                "For small repair tasks, prefer one implementation task plus one validation task at most. "
                "Use subtasks only when they each produce code or run validation."
            )
        if self.swarm_type in {SwarmType.CODING, SwarmType.DEBUGGING, SwarmType.REFACTORING}:
            return (
                "Every file operation must include all required fields. "
                "Do not emit empty writes, missing-content writes, missing patch text, or no-op replace_block operations. "
                "If exact old/new matching is uncertain, prefer a full-file write. "
                "For simple bug fixes or small files, prefer a full-file write or ast_replace_function over fragile block replacement. "
                "Change only the relevant files and include validation commands. "
                "Only emit runnable commands with allowed prefixes such as python, pytest, npm, cargo, go, git, pwsh, or powershell. "
                "Do not emit shell builtins or pseudo-tools like type, cat, ls, dir, read_file, or Get-Content. "
                "For simple file verification, prefer python -c commands."
            )
        if self.swarm_type == SwarmType.TESTING:
            return (
                "Return only runnable validation commands. Prefer targeted tests before broad suites when both are useful. "
                "Use python -c for simple file existence or content checks instead of shell builtins."
            )
        if self.swarm_type == SwarmType.SECURITY:
            return (
                "Recommend only real security or validation commands that are safe to execute locally. "
                "Avoid shell builtins and prefer python -c for simple file inspection."
            )
        return "Respond with strict JSON only."

    async def run_structured(self, session_id: str, context: Dict[str, Any], schema_instructions: str) -> Dict[str, Any]:
        self.session_id = session_id
        await self.initialize_agents(session_id=session_id)
        if self._cancelled:
            return {"error": "cancelled"}
        prompt = f"""
Objective: {self.objective}

Context JSON:
{json.dumps(context, indent=2)}

Return JSON only.
Additional rules:
{self._swarm_rules()}

Schema requirements:
{schema_instructions}
""".strip()
        self.status = "executing"
        for agent in self.agents:
            agent.transition_to(AgentStatus.THINKING, action=self.objective)
        await self.db.update_swarm_status(self.id, "executing")
        base_system = {"role": "system", "content": f"You are VIKI {self.swarm_type.value} swarm. Respond with strict JSON only."}
        base_user = {"role": "user", "content": prompt}
        response: Dict[str, Any] | None = None
        parsed: Dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            messages = [base_system, base_user]
            if attempt > 1:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was not valid JSON for the required schema. "
                            "Return strict JSON only with no markdown, commentary, or prose."
                        ),
                    }
                )
            try:
                response = await asyncio.wait_for(
                    self.provider.complete(
                        self._model_alias(),
                        messages,
                        temperature=0.0,
                        max_tokens=6000,
                        timeout=self.config.timeout_seconds,
                    ),
                    timeout=self.config.timeout_seconds,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    raise
                continue
            try:
                parsed = self._extract_json(response.get("content", "{}"))
                break
            except Exception as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    raise RuntimeError(f"{self.swarm_type.value} swarm returned invalid structured output: {exc}") from exc
        if response is None or parsed is None:
            raise RuntimeError(f"{self.swarm_type.value} swarm returned no structured output: {last_error}")
        for agent in self.agents:
            agent.transition_to(AgentStatus.DONE)
        self.results = {
            "swarm_id": self.id,
            "type": self.swarm_type.value,
            "result": parsed,
            "model": response.get("model"),
            "provider": response.get("provider"),
        }
        usage = response.get("usage", {})
        self.metrics.record_api_call(response.get("model", self._model_alias()), 0.0, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        await self.db.update_swarm_status(self.id, "completed", self.results)
        self.status = "completed"
        return parsed

    async def cancel(self):
        self._cancelled = True
        self.status = "cancelled"
        for agent in self.agents:
            agent.transition_to(AgentStatus.CANCELLED)
        await self.db.update_swarm_status(self.id, "cancelled")
