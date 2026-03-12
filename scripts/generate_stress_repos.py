from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from viki.evals.stress import generate_stress_repos


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate VIKI synthetic stress repositories.")
    parser.add_argument("--output", default="synthetic_stress_repos", help="Destination directory")
    args = parser.parse_args()
    manifest = generate_stress_repos(Path(args.output))
    print(json.dumps({"output": str(Path(args.output).resolve()), "repos": manifest}, indent=2))


if __name__ == "__main__":
    main()
