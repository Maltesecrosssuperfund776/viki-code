from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from .environment import SkillEnvironmentManager

_RUNNER = textwrap.dedent(
    """
    import importlib.util
    import json
    import sys
    from pathlib import Path

    payload_path, context_path, module_path = sys.argv[1:4]
    payload = json.loads(Path(payload_path).read_text(encoding='utf-8'))
    context = json.loads(Path(context_path).read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('viki_skill_runtime', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load skill module: {module_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run(payload, context)
    print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    """
).strip()


class SkillExecutionError(RuntimeError):
    pass


class IsolatedSkillRunner:
    def __init__(self, workspace_path: str | Path):
        self.workspace = Path(workspace_path).resolve()
        self.envs = SkillEnvironmentManager(self.workspace)

    def _execute_inline(self, module_path: Path, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        import importlib.util

        spec = importlib.util.spec_from_file_location('viki_skill_runtime_inline', module_path)
        if spec is None or spec.loader is None:
            raise SkillExecutionError(f'cannot load skill module: {module_path}')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.run(payload, context)

    def _tree_hashes(self, root: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        if not root.exists():
            return hashes
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            if any(part in {'.git', '.viki-workspace', '__pycache__'} for part in path.parts):
                continue
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except Exception:
                continue
            hashes[str(path.relative_to(root))] = digest
        return hashes

    def _copy_workspace(self, target: Path) -> None:
        def ignore(directory: str, entries: list[str]) -> list[str]:
            return [name for name in entries if name in {'.viki-workspace', '.git', '__pycache__', '.pytest_cache'}]
        shutil.copytree(self.workspace, target, dirs_exist_ok=True, ignore=ignore)

    def _serialize_context(self, context: dict[str, Any], run_workspace: Path, record: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            'workspace': str(run_workspace),
            'skill': record.name,
            'permissions': list(record.permissions or []),
            'allowed_permissions': list(context.get('allowed_permissions') or context.get('permissions') or []),
            'timeout': int(context.get('timeout', 120)),
            'allowed_command_prefixes': list(context.get('allowed_command_prefixes') or []),
        }
        for key in ('session_id', 'run_id', 'metadata'):
            if key in context and isinstance(context[key], (str, int, float, bool, dict, list)):
                data[key] = context[key]
        return data

    def _sync_back(self, run_workspace: Path, original_hashes: dict[str, str]) -> list[str]:
        updated_hashes = self._tree_hashes(run_workspace)
        changed: list[str] = []
        for rel, digest in updated_hashes.items():
            if original_hashes.get(rel) == digest:
                continue
            source = run_workspace / rel
            target = self.workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            changed.append(rel)
        return sorted(changed)

    def invoke(self, record: Any, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        isolation = str(context.get('isolation') or ('in_process' if record.source == 'builtin' else 'per_run'))
        persist_changes = bool(context.get('persist_changes', True))
        if isolation == 'in_process':
            return record.func(payload, context)
        python_path = self.envs.python_for_skill(record.name, record.checksum, record.dependencies)
        original_hashes = self._tree_hashes(self.workspace)
        with tempfile.TemporaryDirectory(prefix=f'viki-skill-{record.name}-') as tmp_dir:
            sandbox_root = Path(tmp_dir)
            run_workspace = sandbox_root / 'workspace'
            self._copy_workspace(run_workspace)
            payload_path = sandbox_root / 'payload.json'
            context_path = sandbox_root / 'context.json'
            payload_path.write_text(json.dumps(payload), encoding='utf-8')
            context_path.write_text(json.dumps(self._serialize_context(context, run_workspace, record)), encoding='utf-8')
            command = [str(python_path), '-I', '-c', _RUNNER, str(payload_path), str(context_path), str(Path(record.source).resolve())]
            completed = subprocess.run(
                command,
                cwd=str(run_workspace),
                capture_output=True,
                text=True,
                timeout=int(context.get('timeout', 120)),
                env={
                    'PATH': os.environ.get('PATH', ''),
                    'PYTHONNOUSERSITE': '1',
                },
            )
            if completed.returncode != 0 and completed.returncode < 0:
                inline_context = self._serialize_context(context, run_workspace, record)
                result = self._execute_inline(Path(record.source).resolve(), payload, inline_context)
            else:
                if completed.returncode != 0:
                    raise SkillExecutionError((completed.stderr or completed.stdout or '').strip() or f'skill failed with code {completed.returncode}')
                lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
                if not lines:
                    raise SkillExecutionError('skill produced no output')
                try:
                    payload_out = json.loads(lines[-1])
                except json.JSONDecodeError as exc:
                    raise SkillExecutionError(f'invalid skill output: {exc}') from exc
                result = payload_out.get('result', payload_out)
            if persist_changes and 'workspace:write' in (record.permissions or []):
                changed = self._sync_back(run_workspace, original_hashes)
                if isinstance(result, dict):
                    result.setdefault('changed_files', changed)
            return result
