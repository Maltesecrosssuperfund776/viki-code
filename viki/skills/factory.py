from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Iterable

import yaml

from ..config import settings
from ..infrastructure.security import SecurityScanner
from .environment import SkillEnvironmentManager


SKILL_TEMPLATES: dict[str, dict[str, Any]] = {
    "workspace_reader": {
        "description": "Read one or more workspace files and return their contents.",
        "permissions": ["workspace:read"],
        "dependencies": [],
        "code": lambda name, description: dedent(
            f'''
            SKILL_NAME = "{name}"
            SKILL_DESCRIPTION = {description!r}

            from pathlib import Path

            def run(payload, context):
                root = Path(context.get("workspace") or ".").resolve()
                files = payload.get("files") or []
                output = {{}}
                for item in files:
                    path = (root / item).resolve()
                    if not str(path).startswith(str(root)):
                        output[item] = {{"error": "outside workspace"}}
                        continue
                    if not path.exists():
                        output[item] = {{"error": "missing"}}
                        continue
                    output[item] = {{"content": path.read_text(encoding="utf-8")}}
                return {{"status": "ok", "files": output}}
            '''
        ).strip() + "\n",
    },
    "command_runner": {
        "description": "Run safe developer commands and capture stdout/stderr.",
        "permissions": ["workspace:read", "command:run"],
        "dependencies": [],
        "code": lambda name, description: dedent(
            f'''
            SKILL_NAME = "{name}"
            SKILL_DESCRIPTION = {description!r}

            import shlex
            import subprocess
            from pathlib import Path

            def _prefix_allowed(tokens, allowed):
                return bool(tokens) and tokens[0] in set(allowed or [])

            def run(payload, context):
                command = str(payload.get("command") or "").strip()
                if not command:
                    return {{"status": "error", "message": "missing command"}}
                try:
                    tokens = shlex.split(command)
                except ValueError:
                    return {{"status": "blocked", "message": "malformed command"}}
                if not _prefix_allowed(tokens, context.get("allowed_command_prefixes") or ["python", "pytest", "git", "make", "npm", "node"]):
                    return {{"status": "blocked", "message": "command prefix not allowed"}}
                workspace = Path(context.get("workspace") or ".").resolve()
                completed = subprocess.run(
                    tokens,
                    cwd=str(workspace),
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=int(payload.get("timeout") or 60),
                )
                return {{
                    "status": "ok" if completed.returncode == 0 else "failed",
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }}
            '''
        ).strip() + "\n",
    },
    "patch_writer": {
        "description": "Write or replace a file inside the workspace from payload content.",
        "permissions": ["workspace:read", "workspace:write"],
        "dependencies": [],
        "code": lambda name, description: dedent(
            f'''
            SKILL_NAME = "{name}"
            SKILL_DESCRIPTION = {description!r}

            from pathlib import Path

            def run(payload, context):
                workspace = Path(context.get("workspace") or ".").resolve()
                relative = payload.get("path")
                content = payload.get("content")
                if not relative or content is None:
                    return {{"status": "error", "message": "path and content are required"}}
                target = (workspace / relative).resolve()
                if not str(target).startswith(str(workspace)):
                    return {{"status": "blocked", "message": "outside workspace"}}
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(content), encoding="utf-8")
                return {{"status": "ok", "path": relative, "bytes": len(str(content).encode("utf-8"))}}
            '''
        ).strip() + "\n",
    },
}


class AutoSkillFactory:
    def __init__(self, workspace_path: str | Path, provider: Any | None = None):
        self.workspace = Path(workspace_path).resolve()
        self.provider = provider
        self.skill_root = self.workspace / settings.skill_dir
        self.skill_root.mkdir(parents=True, exist_ok=True)
        self.security = SecurityScanner()
        self.environments = SkillEnvironmentManager(self.workspace)

    def _slug(self, text: str) -> str:
        return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_") or "generated_skill"

    def available_templates(self) -> list[str]:
        return sorted(SKILL_TEMPLATES)

    def _template_payload(self, template: str, name: str, description: str) -> dict[str, Any]:
        chosen = SKILL_TEMPLATES[template]
        python_code = chosen["code"](name, description)
        return {
            "SKILL_NAME": name,
            "SKILL_DESCRIPTION": description,
            "python_code": python_code,
            "permissions": list(chosen["permissions"]),
            "dependencies": list(chosen["dependencies"]),
            "template": template,
            "isolation": "per_run",
        }

    async def _model_payload(self, description: str) -> dict[str, Any] | None:
        if self.provider is None or not getattr(self.provider, "validate_config", lambda: False)():
            return None
        prompt = dedent(
            f"""
            Create a VIKI skill as strict JSON.
            The skill must expose:
            - SKILL_NAME string
            - SKILL_DESCRIPTION string
            - python_code string containing a pure-python module with function run(payload, context) -> dict
            - permissions array from: workspace:read, workspace:write, command:run
            - dependencies array using pinned package specs when needed
            - isolation string using one of: per_run, in_process
            The skill should satisfy: {description}
            Avoid network calls. Stay within local workspace operations.
            Return JSON only.
            """
        )
        try:
            response = await self.provider.complete(
                "coding",
                [
                    {"role": "system", "content": "You generate VIKI skill modules. JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4000,
            )
            text = response.get("content", "{}")
            start, end = text.find("{"), text.rfind("}")
            return json.loads(text[start : end + 1])
        except Exception:
            return None

    async def create_skill(
        self,
        description: str,
        preferred_name: str | None = None,
        template: str | None = None,
        permissions: Iterable[str] | None = None,
        dependencies: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        slug = self._slug(preferred_name or description)
        skill_dir = self.skill_root / slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / "main.py"

        name = preferred_name or slug
        payload: dict[str, Any] | None = None
        if template:
            if template not in SKILL_TEMPLATES:
                raise ValueError(f"Unknown skill template: {template}")
            payload = self._template_payload(template, name, description)
        else:
            payload = await self._model_payload(description)
        if payload is None:
            payload = self._template_payload("workspace_reader", name, description)
            payload["permissions"] = ["workspace:read"]
            payload["template"] = "fallback"

        if permissions is not None:
            payload["permissions"] = list(permissions)
        if dependencies is not None:
            payload["dependencies"] = self.environments.validate_dependencies(list(dependencies))
        else:
            payload["dependencies"] = self.environments.validate_dependencies(payload.get("dependencies", []))

        code = payload["python_code"]
        safe, violations = self.security.scan_code(code, str(path))
        if not safe:
            raise ValueError(f"Generated skill rejected by security scan: {violations}")

        path.write_text(code, encoding="utf-8", newline="\n")
        checksum = hashlib.sha256(code.replace("\r\n", "\n").encode("utf-8")).hexdigest()
        manifest = {
            "name": payload.get("SKILL_NAME") or name,
            "description": payload.get("SKILL_DESCRIPTION", description),
            "version": payload.get("version", "0.1.0"),
            "permissions": payload.get("permissions", ["workspace:read"]),
            "dependencies": payload.get("dependencies", []),
            "entrypoint": "main.py",
            "checksum": checksum,
            "template": payload.get("template", template or "generated"),
            "signed": False,
            "isolation": payload.get("isolation", "per_run"),
        }
        manifest_path = skill_dir / settings.skill_manifest_name
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n")
        return {
            "name": manifest["name"],
            "description": manifest["description"],
            "path": str(path),
            "manifest": str(manifest_path),
            "checksum": checksum,
            "template": manifest["template"],
        }
