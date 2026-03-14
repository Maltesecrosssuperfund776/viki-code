from __future__ import annotations

import os
import platform
import shutil
import site
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath


@dataclass(frozen=True)
class PlatformProfile:
    os_name: str
    family: str
    shell: str
    shell_flag: str
    python_executable: str
    venv_python: str
    launcher_name: str
    launcher_hint: str


class PlatformSupport:
    @staticmethod
    def current() -> PlatformProfile:
        system = platform.system().lower()
        python_name = Path(os.environ.get("PYTHON", "python")).name or "python"
        if system.startswith("win"):
            shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
            return PlatformProfile(
                os_name="windows",
                family="windows",
                shell=shell,
                shell_flag="-Command",
                python_executable=python_name,
                venv_python=r"Scripts\python.exe",
                launcher_name="viki-local.cmd",
                launcher_hint=r".viki-workspace\bin\viki-local.cmd up .",
            )
        if system == "darwin":
            shell = shutil.which("zsh") or shutil.which("bash") or "/bin/zsh"
            return PlatformProfile(
                os_name="macos",
                family="unix",
                shell=shell,
                shell_flag="-lc",
                python_executable=python_name,
                venv_python="bin/python",
                launcher_name="viki-local",
                launcher_hint=".viki-workspace/bin/viki-local up .",
            )
        shell = shutil.which("bash") or shutil.which("sh") or "/bin/bash"
        return PlatformProfile(
            os_name="linux",
            family="unix",
            shell=shell,
            shell_flag="-lc",
            python_executable=python_name,
            venv_python="bin/python",
            launcher_name="viki-local",
            launcher_hint=".viki-workspace/bin/viki-local up .",
        )

    @staticmethod
    def venv_python(venv_dir: Path, profile: PlatformProfile | None = None) -> Path:
        active = profile or PlatformSupport.current()
        if active.family == "windows":
            return PureWindowsPath(str(venv_dir)) / PureWindowsPath(active.venv_python)
        return PurePosixPath(venv_dir.as_posix()) / PurePosixPath(active.venv_python)

    @staticmethod
    def write_local_launchers(root: Path, python_bin: Path) -> list[str]:
        bin_dir = root / ".viki-workspace" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        unix_launcher = bin_dir / "viki-local"
        unix_launcher.write_text(
            "#!/usr/bin/env sh\n"
            f'"{python_bin}" -m viki.cli "$@"\n',
            encoding="utf-8",
        )
        unix_launcher.chmod(0o755)
        written.append(str(unix_launcher))

        cmd_launcher = bin_dir / "viki-local.cmd"
        cmd_launcher.write_text(
            "@echo off\r\n"
            f'"{python_bin}" -m viki.cli %*\r\n',
            encoding="utf-8",
        )
        written.append(str(cmd_launcher))

        ps_launcher = bin_dir / "viki-local.ps1"
        ps_launcher.write_text(
            f'& "{python_bin}" -m viki.cli @args\n',
            encoding="utf-8",
        )
        written.append(str(ps_launcher))
        return written

    @staticmethod
    def user_bin_dir(profile: PlatformProfile | None = None) -> Path:
        active = profile or PlatformSupport.current()
        base = Path(site.getuserbase())
        return base / ("Scripts" if active.family == "windows" else "bin")

    @staticmethod
    def write_user_launchers(python_bin: Path, profile: PlatformProfile | None = None) -> list[str]:
        active = profile or PlatformSupport.current()
        bin_dir = PlatformSupport.user_bin_dir(active)
        bin_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        unix_launcher = bin_dir / "viki"
        unix_launcher.write_text(
            "#!/usr/bin/env sh\n"
            f'"{python_bin}" -m viki.cli "$@"\n',
            encoding="utf-8",
        )
        unix_launcher.chmod(0o755)
        written.append(str(unix_launcher))

        cmd_launcher = bin_dir / "viki.cmd"
        cmd_launcher.write_text(
            "@echo off\r\n"
            f'"{python_bin}" -m viki.cli %*\r\n',
            encoding="utf-8",
        )
        written.append(str(cmd_launcher))

        ps_launcher = bin_dir / "viki.ps1"
        ps_launcher.write_text(
            f'& "{python_bin}" -m viki.cli @args\n',
            encoding="utf-8",
        )
        written.append(str(ps_launcher))
        return written
