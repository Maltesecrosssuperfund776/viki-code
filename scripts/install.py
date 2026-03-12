from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal VIKI installer for Windows, macOS, and Linux.")
    parser.add_argument("--path", default=".", help="Path to the VIKI repository")
    parser.add_argument("--run", action="store_true", help="Start VIKI after install")
    parser.add_argument("--dry-run", action="store_true", help="Validate bootstrap/install flow without starting VIKI")
    parser.add_argument("--dev", action="store_true", help="Install dev dependencies")
    parser.add_argument("--force-env", action="store_true", help="Rewrite .env template")
    parser.add_argument("--update", action="store_true", help="Upgrade the local VIKI install in place")
    parser.add_argument("--uninstall", action="store_true", help="Remove local VIKI workspace artifacts and virtualenv")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8787")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if args.uninstall:
        removed = []
        for relative in [".venv", ".viki-workspace"]:
            target = root / relative
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                removed.append(str(target))
        print({"uninstalled": True, "removed": removed})
        raise SystemExit(0)

    bootstrap = root / "scripts" / "bootstrap.py"
    cmd = [sys.executable, str(bootstrap), "--path", str(root)]
    if args.run:
        cmd.append("--run")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.dev:
        cmd.append("--dev")
    if args.force_env:
        cmd.append("--force-env")
    if args.update:
        cmd.append("--update")
    cmd.extend(["--host", str(args.host), "--port", str(args.port)])
    raise SystemExit(subprocess.call(cmd, cwd=str(root)))


if __name__ == "__main__":
    main()
