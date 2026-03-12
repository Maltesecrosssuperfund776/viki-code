from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from . import __version__
from .api.server import create_app
from .config import settings
from .core.hive import HiveMind
from .core.repo_index import RepoIndex
from .evals.suite import BenchmarkSuite
from .evals.scripted_provider import ScriptedEvalProvider
from .ide.vscode import VSCodeIntegrator
from .infrastructure.database import DatabaseManager
from .infrastructure.observability import setup_logging, start_metrics_server
from .infrastructure.security import ContainerRuntimeProbe
from .integrations.telegram import TelegramBotClient
from .integrations.whatsapp import TwilioWhatsAppClient
from .platforms import PlatformSupport
from .providers.litellm_provider import LiteLLMProvider
from .skills.factory import AutoSkillFactory
from .skills.package import SkillPackageManager
from .skills.registry import SkillRegistry

app = typer.Typer(help="VIKI Code - production-oriented swarm coding system")
skills_app = typer.Typer(help="Manage VIKI skills")
approvals_app = typer.Typer(help="Review approval queue")
ide_app = typer.Typer(help="IDE integration commands")
evals_app = typer.Typer(help="Benchmark and eval suite")
integrations_app = typer.Typer(help="Messaging integrations")
app.add_typer(skills_app, name="skills")
app.add_typer(approvals_app, name="approvals")
app.add_typer(ide_app, name="ide")
app.add_typer(evals_app, name="evals")
app.add_typer(integrations_app, name="integrations")
console = Console()


def _workspace_root(path: Path) -> Path:
    return path.resolve()


def _db_for_root(root: Path) -> DatabaseManager:
    return DatabaseManager(str(root / settings.workspace_dir / "viki.db"))


def _ensure_initialized(root: Path, force_env: bool = False) -> Path:
    workspace = settings.ensure_workspace(root)
    env_path = root / ".env"
    if force_env or not env_path.exists():
        env_path.write_text(_env_template(root / settings.workspace_dir / "viki.db"), encoding="utf-8")
    return workspace


def _env_template(workspace_db: Path) -> str:
    return f"""# VIKI routing
VIKI_REASONING_MODEL=
VIKI_CODING_MODEL=
VIKI_FAST_MODEL=

# Primary providers
OPENROUTER_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
DEEPSEEK_API_KEY=
GROQ_API_KEY=
MISTRAL_API_KEY=
TOGETHERAI_API_KEY=
FIREWORKS_API_KEY=
XAI_API_KEY=
CEREBRAS_API_KEY=
SAMBANOVA_API_KEY=
AZURE_API_KEY=
AZURE_API_BASE=
AZURE_API_VERSION=
OPENAI_API_BASE=
OPENAI_COMPAT_MODEL=
OLLAMA_BASE_URL=
OLLAMA_MODEL=

# Runtime
SANDBOX_ENABLED=true
MAX_COST_PER_TASK_USD=10
LOG_LEVEL=INFO
APPROVAL_MODE=auto
API_HOST={settings.api_host}
API_PORT={settings.api_port}
DATABASE_URL=sqlite:///{workspace_db}

# Telegram
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ALLOWED_CHAT_IDS=

# WhatsApp via Twilio
WHATSAPP_ENABLED=false
WHATSAPP_ACCOUNT_SID=
WHATSAPP_AUTH_TOKEN=
WHATSAPP_FROM_NUMBER=whatsapp:+0000000000
WHATSAPP_ALLOWED_SENDERS=
WHATSAPP_VALIDATE_SIGNATURE=true
WHATSAPP_WEBHOOK_URL=
"""


@app.command()
def init(path: Path = typer.Argument(Path('.'), help="Workspace root"), force: bool = typer.Option(False, "--force", "-f")):
    root = _workspace_root(path)
    workspace = root / settings.workspace_dir
    if workspace.exists() and not force:
        rprint("[yellow]Workspace already initialized. Use --force to regenerate the template.[/yellow]")
        raise typer.Exit(1)
    workspace = _ensure_initialized(root, force_env=force)
    rprint(f"[green]Initialized VIKI workspace at {workspace}[/green]")
    rprint("[blue]Edit .env, then run: viki doctor[/blue]")


@app.command()
def up(
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
    host: str = typer.Option(settings.api_host, "--host"),
    port: int = typer.Option(settings.api_port, "--port"),
    force_env: bool = typer.Option(False, "--force-env", help="Rewrite .env template before starting"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Prepare workspace without starting the API server"),
):
    root = _workspace_root(path)
    workspace = _ensure_initialized(root, force_env=force_env)
    PlatformSupport.write_local_launchers(root, Path(sys.executable).resolve())
    rprint(f"[green]VIKI workspace ready at {workspace}[/green]")
    if dry_run:
        rprint(f"[blue]Dry run complete. Start with: viki up {root}[/blue]")
        return
    rprint(f"[blue]Starting VIKI API on http://{host}:{port}[/blue]")
    app_instance = create_app(root)
    uvicorn.run(app_instance, host=host, port=port)


@app.command()
def doctor(path: Path = typer.Argument(Path('.'), help="Workspace root")):
    root = _workspace_root(path)
    setup_logging(settings.log_level, settings.structured_logging)
    provider = LiteLLMProvider()
    profile = PlatformSupport.current()
    table = Table(title="VIKI Doctor")
    table.add_column("Check")
    table.add_column("Status")

    workspace = root / settings.workspace_dir
    table.add_row("Workspace", "OK" if workspace.exists() else "Missing")
    table.add_row("Platform", profile.os_name)
    table.add_row("Shell", profile.shell)
    table.add_row("LiteLLM", "OK" if provider._available else "Missing")
    active_backends = provider.available_backends() if provider._available else []
    table.add_row("Providers", ", ".join(active_backends) if active_backends else "No API backend configured")

    try:
        import docker
        client = docker.from_env()
        client.ping()
        docker_status = "OK"
    except Exception:
        docker_status = "Unavailable"
    table.add_row("Docker", docker_status)

    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        git_status = "OK"
    except Exception:
        git_status = "Unavailable"
    table.add_row("Git", git_status)
    runtimes = ContainerRuntimeProbe().probe_all()
    best_runtime = ContainerRuntimeProbe().best_available(runtimes)
    table.add_row("Isolation runtime", f"{best_runtime.name}:{best_runtime.detail}" if best_runtime else "None available")

    registry = SkillRegistry(root)
    table.add_row("Skills", str(len(registry.list_skills())))
    table.add_row("Approvals", settings.approval_mode)
    table.add_row("API", f"{settings.api_host}:{settings.api_port}")
    table.add_row("Launcher", profile.launcher_hint)
    console.print(table)


@app.command("platforms")
def platform_info():
    profile = PlatformSupport.current()
    table = Table(title="VIKI Platform Support")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("OS", profile.os_name)
    table.add_row("Family", profile.family)
    table.add_row("Shell", profile.shell)
    table.add_row("Python", profile.python_executable)
    table.add_row("Venv Python", profile.venv_python)
    table.add_row("Launcher", profile.launcher_name)
    table.add_row("Shortcut", profile.launcher_hint)
    console.print(table)


@app.command()
def version():
    console.print(__version__)


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Task for VIKI"),
    mode: str = typer.Option("standard", "--mode", "-m"),
    path: Path = typer.Option(Path('.'), "--path", help="Workspace root"),
    detach: bool = typer.Option(False, "--detach", "-d"),
    background_child: bool = typer.Option(False, "--background-child", hidden=True),
):
    root = _workspace_root(path)
    if not (root / settings.workspace_dir).exists():
        rprint("[red]Workspace not initialized. Run 'viki init' first.[/red]")
        raise typer.Exit(1)

    if detach and not background_child:
        cmd = [sys.executable, "-m", "viki.cli", "run", prompt, "--mode", mode, "--path", str(root), "--background-child"]
        proc = subprocess.Popen(cmd, cwd=str(root))
        rprint(f"[green]Detached VIKI run started with PID {proc.pid}[/green]")
        return

    setup_logging(settings.log_level, settings.structured_logging)
    if settings.metrics_enabled:
        start_metrics_server(settings.metrics_port)
    provider = LiteLLMProvider()
    if not provider.validate_config():
        rprint("[red]No provider configuration detected. Add at least one API backend in .env.[/red]")
        raise typer.Exit(1)

    async def main():
        hive = HiveMind(provider, str(root))
        await hive.initialize()
        try:
            result = await hive.process_request(prompt, mode=mode)
        finally:
            await hive.shutdown()
        console.print(f"[bold green]Session {result['session_id']}[/bold green]")
        console.print(f"Status: {result['status']}")
        if result["changed_files"]:
            console.print("Changed files:")
            for path_item in result["changed_files"]:
                console.print(f"  - {path_item}")
        if result["created_skills"]:
            console.print("Created skills:")
            for item in result["created_skills"]:
                console.print(f"  - {item['name']}: {item['path']}")
        if result["pending_approvals"]:
            console.print("Pending approvals:")
            for item in result["pending_approvals"]:
                console.print(f"  - #{item['id']} {item['subject']} (risk {item['risk_score']})")
        failing = [entry for entry in result["commands"] if entry.get("returncode") not in (0, None)]
        if failing:
            console.print("[yellow]Commands with non-zero exit codes:[/yellow]")
            for entry in failing:
                console.print(f"  - {entry.get('command')}: {entry.get('returncode')}")
        return result

    try:
        asyncio.run(main())
    except Exception as exc:
        rprint(f"[red]VIKI run failed: {exc}[/red]")
        raise typer.Exit(1)


@app.command()
def repo(
    query: str = typer.Argument("repo overview", help="Repo search query"),
    path: Path = typer.Option(Path('.'), "--path", help="Workspace root"),
    limit: int = typer.Option(12, "--limit", help="Number of matches to show"),
):
    root = _workspace_root(path)
    index = RepoIndex(root)
    payload = index.context_pack(query, limit=limit)
    console.print_json(json.dumps(payload))


@app.command()
def symbols(
    query: str = typer.Argument("", help="Symbol search query"),
    path: Path = typer.Option(Path('.'), "--path", help="Workspace root"),
    file: list[str] = typer.Option([], "--file", help="Restrict to one or more repo paths"),
    limit: int = typer.Option(20, "--limit", help="Number of symbols to show"),
):
    root = _workspace_root(path)
    index = RepoIndex(root)
    payload = {"query": query, "items": index.symbols(query=query, paths=file, limit=limit)}
    console.print_json(json.dumps(payload))


@app.command()
def impact(
    changed_file: list[str] = typer.Option([], "--changed-file", help="Changed file path, repeat for multiple entries"),
    path: Path = typer.Option(Path('.'), "--path", help="Workspace root"),
    limit: int = typer.Option(20, "--limit", help="Neighbor/test limit"),
):
    root = _workspace_root(path)
    index = RepoIndex(root)
    payload = index.impact_report(changed_file, limit=limit)
    console.print_json(json.dumps(payload))


@app.command()
def diff(
    session_id: str = typer.Argument(..., help="Session id to inspect"),
    path: Path = typer.Option(Path('.'), "--path", help="Workspace root"),
):
    root = _workspace_root(path)
    db = _db_for_root(root)

    async def main():
        await db.initialize()
        session = await db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found: {session_id}[/red]")
            raise typer.Exit(1)
        payload = session.get("result_json")
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        payload = payload or {}
        console.print_json(json.dumps({"diff_preview": payload.get("diff_preview", []), "patch_bundles": payload.get("patch_bundles", [])}))

    asyncio.run(main())


@app.command()
def status(path: Path = typer.Argument(Path('.'), help="Workspace root"), session_id: Optional[str] = typer.Option(None, "--session-id")):
    root = _workspace_root(path)
    db = _db_for_root(root)

    async def main():
        await db.initialize()
        if session_id:
            session = await db.get_session(session_id)
            console.print_json(json.dumps(session or {}))
            return
        sessions = await db.get_recent_sessions(10)
        table = Table(title="Recent VIKI sessions")
        table.add_column("Session")
        table.add_column("Status")
        table.add_column("Request")
        for item in sessions:
            table.add_row(item["id"], item.get("status", "?"), (item.get("user_request") or "")[:60])
        console.print(table)

    asyncio.run(main())


@app.command()
def resume(path: Path = typer.Argument(Path('.'), help="Workspace root")):
    root = _workspace_root(path)
    provider = LiteLLMProvider()

    async def main():
        hive = HiveMind(provider, str(root))
        await hive.initialize()
        state = await hive.resume_last_session()
        console.print_json(json.dumps(state))

    asyncio.run(main())


@app.command()
def tui(path: Path = typer.Argument(Path('.'), help="Workspace root")):
    from .ui.dashboard import launch_dashboard

    root = _workspace_root(path)
    launch_dashboard(root / settings.workspace_dir / "viki.db")


@app.command()
def serve(path: Path = typer.Argument(Path('.'), help="Workspace root"), host: str = typer.Option(settings.api_host), port: int = typer.Option(settings.api_port)):
    root = _workspace_root(path)
    app_instance = create_app(root)
    uvicorn.run(app_instance, host=host, port=port)


@skills_app.command("list")
def skills_list(path: Path = typer.Argument(Path('.'), help="Workspace root")):
    registry = SkillRegistry(_workspace_root(path))
    table = Table(title="VIKI Skills")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Permissions")
    table.add_column("Trust")
    table.add_column("Source")
    table.add_column("Description")
    for record in registry.list_skills():
        trust = "signed" if record.signed else record.integrity
        table.add_row(record.name, record.version, ", ".join(record.permissions or []), trust, record.source, record.description)
    console.print(table)


@skills_app.command("templates")
def skills_templates(path: Path = typer.Argument(Path('.'), help="Workspace root")):
    factory = AutoSkillFactory(_workspace_root(path), provider=None)
    table = Table(title="VIKI Skill Templates")
    table.add_column("Template")
    table.add_column("Use")
    for name in factory.available_templates():
        table.add_row(name, f"viki skills create \"...\" --template {name}")
    console.print(table)


@skills_app.command("init")
def skills_init(
    name: str = typer.Argument(..., help="Skill name"),
    description: str = typer.Option(..., "--description", help="Skill description"),
    template: str = typer.Option("workspace_reader", "--template", help="Skill template"),
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
):
    factory = AutoSkillFactory(_workspace_root(path), provider=None)

    async def main():
        result = await factory.create_skill(description, preferred_name=name, template=template)
        console.print_json(json.dumps(result))

    asyncio.run(main())


@skills_app.command("create")
def skills_create(
    description: str = typer.Argument(...),
    name: Optional[str] = typer.Option(None, "--name"),
    template: Optional[str] = typer.Option(None, "--template", help="Use a local template instead of provider generation"),
    permission: list[str] = typer.Option([], "--permission", help="Explicit permission, repeat for multiple entries"),
    dependency: list[str] = typer.Option([], "--dependency", help="Pinned package requirement, repeat for multiple entries"),
    path: Path = typer.Argument(Path('.')),
):
    provider = LiteLLMProvider()
    factory = AutoSkillFactory(_workspace_root(path), provider=provider)

    async def main():
        result = await factory.create_skill(
            description,
            preferred_name=name,
            template=template,
            permissions=permission or None,
            dependencies=dependency or None,
        )
        console.print_json(json.dumps(result))

    asyncio.run(main())


@skills_app.command("pack")
def skills_pack(
    skill_path: Path = typer.Argument(..., help="Directory containing main.py and manifest.yaml"),
    output: Optional[Path] = typer.Option(None, "--output", help="Output archive path"),
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
):
    manager = SkillPackageManager(_workspace_root(path))
    result = manager.pack(skill_path, output_path=output)
    console.print_json(json.dumps(result))


@skills_app.command("install")
def skills_install(
    archive: Path = typer.Argument(..., help="Local .vskill.zip archive"),
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
):
    manager = SkillPackageManager(_workspace_root(path))
    result = manager.install(archive)
    console.print_json(json.dumps(result))


@skills_app.command("prepare-env")
def skills_prepare_env(
    name: str = typer.Argument(..., help="Skill name"),
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
    upgrade: bool = typer.Option(False, "--upgrade", help="Recreate the skill environment before installing dependencies"),
):
    registry = SkillRegistry(_workspace_root(path))
    result = registry.prepare_environment(name, upgrade=upgrade)
    console.print_json(json.dumps(result))


@skills_app.command("invoke")
def skills_invoke(
    name: str = typer.Argument(..., help="Skill name"),
    payload: str = typer.Option("{}", "--payload", help="JSON payload passed to the skill"),
    permission: list[str] = typer.Option([], "--permission", help="Granted permission, repeat for multiple entries"),
    isolation: str = typer.Option("", "--isolation", help="Override isolation mode for this run"),
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
):
    registry = SkillRegistry(_workspace_root(path))
    try:
        parsed_payload = json.loads(payload)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid payload JSON: {exc}[/red]")
        raise typer.Exit(1)
    context = {
        "workspace": str(_workspace_root(path)),
        "allowed_permissions": permission or ["workspace:read", "workspace:write", "command:run"],
        "isolation": isolation or None,
    }
    result = registry.invoke(name, parsed_payload, context)
    console.print_json(json.dumps(result))


@skills_app.command("validate")
def skills_validate(path: Path = typer.Argument(Path('.'), help="Workspace root")):
    registry = SkillRegistry(_workspace_root(path))
    invalid = []
    for record in registry.list_skills():
        try:
            if record.source != "builtin":
                registry.invoke(
                    record.name,
                    {"files": []} if "workspace:read" in (record.permissions or []) else {},
                    {
                        "workspace": str(_workspace_root(path)),
                        "allowed_permissions": record.permissions or ["workspace:read"],
                        "persist_changes": False,
                    },
                )
        except Exception as exc:
            invalid.append((record.name, str(exc)))
    if invalid:
        for name, error in invalid:
            console.print(f"[red]{name}: {error}[/red]")
        raise typer.Exit(1)
    console.print("[green]All skills loaded successfully[/green]")


@approvals_app.command("list")
def approvals_list(path: Path = typer.Argument(Path('.'), help="Workspace root"), status: str = typer.Option("pending", "--status")):
    root = _workspace_root(path)
    db = _db_for_root(root)

    async def main():
        await db.initialize()
        rows = await db.list_approvals(status=status, limit=100)
        table = Table(title=f"Approvals ({status})")
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Risk")
        table.add_column("Subject")
        for row in rows:
            table.add_row(str(row["id"]), row.get("request_type", ""), str(row.get("risk_score", 0)), row.get("subject", ""))
        console.print(table)

    asyncio.run(main())


@approvals_app.command("approve")
def approvals_approve(approval_id: int = typer.Argument(...), path: Path = typer.Argument(Path('.')), scope: str = typer.Option("once", "--scope")):
    root = _workspace_root(path)
    db = _db_for_root(root)

    async def main():
        await db.initialize()
        await db.resolve_approval(approval_id, status="approved", reviewer=f"cli-user:{scope}")
        console.print(f"[green]Approved #{approval_id} ({scope})[/green]")

    asyncio.run(main())


@approvals_app.command("reject")
def approvals_reject(approval_id: int = typer.Argument(...), path: Path = typer.Argument(Path('.'))):
    root = _workspace_root(path)
    db = _db_for_root(root)

    async def main():
        await db.initialize()
        await db.resolve_approval(approval_id, status="rejected", reviewer="cli-user")
        console.print(f"[yellow]Rejected #{approval_id}[/yellow]")

    asyncio.run(main())


@ide_app.command("vscode")
def ide_vscode(path: Path = typer.Argument(Path('.'), help="Workspace root")):
    root = _workspace_root(path)
    written = VSCodeIntegrator(root).install()
    console.print_json(json.dumps(written))


@ide_app.command("vscode-extension")
def ide_vscode_extension(path: Path = typer.Argument(Path('.'), help="Workspace root")):
    root = _workspace_root(path)
    written = VSCodeIntegrator(root).install_extension_scaffold()
    console.print_json(json.dumps(written))


@evals_app.command("run")
def evals_run(
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
    dataset: list[str] = typer.Option(["public"], "--dataset", help="Benchmark dataset to run; repeat for multiple sets"),
    cases_dir: Optional[Path] = typer.Option(None, "--cases-dir", help="Directory containing benchmark case manifests"),
    agent_name: str = typer.Option("VIKI Code", "--agent-name", help="Agent name recorded in the benchmark report"),
    offline_scripted: bool = typer.Option(False, "--offline-scripted", help="Run the benchmark suite with the deterministic offline provider"),
):
    root = _workspace_root(path)
    provider = ScriptedEvalProvider() if offline_scripted else LiteLLMProvider()
    if not offline_scripted and not provider.validate_config():
        rprint("[red]No provider configuration detected. Add at least one API backend in .env.[/red]")
        raise typer.Exit(1)

    async def main():
        cases = BenchmarkSuite.load_cases(root, datasets=dataset, cases_dir=cases_dir)
        suite = BenchmarkSuite(root, provider, cases=cases or None, agent_name=agent_name)
        report = await suite.run()
        report_path = BenchmarkSuite.save_report(root, report)
        console.print_json(json.dumps({"report": report, "path": str(report_path)}))

    asyncio.run(main())


@evals_app.command("compare")
def evals_compare(
    report: Path = typer.Argument(..., help="Primary benchmark report JSON"),
    baseline: list[str] = typer.Option([], "--baseline", help="Baseline in the form name=path/to/report.json"),
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
):
    baselines = {}
    for item in baseline:
        if "=" not in item:
            console.print(f"[red]Invalid baseline: {item}[/red]")
            raise typer.Exit(1)
        name, report_path = item.split("=", 1)
        baselines[name] = json.loads(Path(report_path).read_text(encoding="utf-8"))
    subject = json.loads(report.read_text(encoding="utf-8"))
    comparison = BenchmarkSuite.compare_reports(subject, baselines)
    output = BenchmarkSuite.save_comparison(_workspace_root(path), comparison)
    console.print_json(json.dumps({"comparison": comparison, "path": str(output)}))


@evals_app.command("publish")
def evals_publish(
    report: Path = typer.Argument(..., help="Benchmark report JSON"),
    comparison: Optional[Path] = typer.Option(None, "--comparison", help="Optional comparison JSON"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Directory where the board is published"),
    path: Path = typer.Argument(Path('.'), help="Workspace root"),
):
    subject = json.loads(report.read_text(encoding="utf-8"))
    comparison_payload = json.loads(comparison.read_text(encoding="utf-8")) if comparison else None
    output = BenchmarkSuite.publish_board(_workspace_root(path), subject, comparison=comparison_payload, output_dir=output_dir)
    console.print_json(json.dumps({"output": str(output)}))


@integrations_app.command("status")
def integrations_status():
    telegram = TelegramBotClient()
    whatsapp = TwilioWhatsAppClient()
    table = Table(title="VIKI Integrations")
    table.add_column("Channel")
    table.add_column("Enabled")
    table.add_column("Policy")
    table.add_row("Telegram", "yes" if telegram.enabled else "no", "secret" if telegram.secret else "open")
    table.add_row("WhatsApp", "yes" if whatsapp.enabled else "no", "signed" if settings.whatsapp_validate_signature else "unsigned")
    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
