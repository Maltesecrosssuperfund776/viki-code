from __future__ import annotations

import asyncio
from pathlib import Path

from typer.testing import CliRunner

from viki.cli import app
from viki.platforms import PlatformProfile, PlatformSupport
from viki.skills.factory import AutoSkillFactory
from viki.skills.package import SkillPackageManager
from viki.skills.registry import SkillRegistry

runner = CliRunner()


def test_platform_support_venv_python_paths():
    win = PlatformProfile(
        os_name="windows",
        family="windows",
        shell="powershell.exe",
        shell_flag="-Command",
        python_executable="python",
        venv_python=r"Scripts\python.exe",
        launcher_name="viki-local.cmd",
        launcher_hint=r".viki-workspace\bin\viki-local.cmd up .",
    )
    unix = PlatformProfile(
        os_name="linux",
        family="unix",
        shell="/bin/bash",
        shell_flag="-lc",
        python_executable="python3",
        venv_python="bin/python",
        launcher_name="viki-local",
        launcher_hint=".viki-workspace/bin/viki-local up .",
    )
    assert str(PlatformSupport.venv_python(Path("/tmp/project/.venv"), unix)).endswith(".venv/bin/python")
    assert str(PlatformSupport.venv_python(Path("C:/project/.venv"), win)).endswith(r"Scripts\python.exe")


def test_local_launchers_are_generated(tmp_path: Path):
    written = PlatformSupport.write_local_launchers(tmp_path, tmp_path / ".venv" / "bin" / "python")
    assert len(written) == 3
    assert (tmp_path / ".viki-workspace" / "bin" / "viki-local").exists()
    assert (tmp_path / ".viki-workspace" / "bin" / "viki-local.cmd").exists()
    assert (tmp_path / ".viki-workspace" / "bin" / "viki-local.ps1").exists()


def test_skill_template_pack_and_install(tmp_path: Path):
    factory = AutoSkillFactory(tmp_path, provider=None)

    async def run_create():
        return await factory.create_skill(
            "Write files into the workspace",
            preferred_name="patch_helper",
            template="patch_writer",
        )

    created = asyncio.run(run_create())
    manager = SkillPackageManager(tmp_path)
    packed = manager.pack(Path(created["path"]).parent)
    assert packed["archive"].endswith(".vskill.zip")

    installed_root = tmp_path / "installed"
    installed_root.mkdir()
    installed = SkillPackageManager(installed_root).install(packed["archive"])
    registry = SkillRegistry(installed_root)
    assert registry.has("patch_helper")
    assert installed["checksum"]


def test_cli_skill_init_and_templates(tmp_path: Path):
    result = runner.invoke(app, ["skills", "templates", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "workspace_reader" in result.output

    result = runner.invoke(
        app,
        [
            "skills",
            "init",
            "repo_reader",
            "--description",
            "Read repo files",
            "--template",
            "workspace_reader",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    registry = SkillRegistry(tmp_path)
    assert registry.has("repo_reader")
