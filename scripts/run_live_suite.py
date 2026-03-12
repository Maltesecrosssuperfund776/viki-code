from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from viki.evals.live_suite import LiveExecutionSuite


def main() -> None:
    parser = argparse.ArgumentParser(description="Run VIKI live execution suite.")
    parser.add_argument("--workspace", default=".", help="VIKI repository/workspace root")
    parser.add_argument("--output", default="LIVE_RUN_RESULTS", help="Directory for redacted live results")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    suite = LiveExecutionSuite(args.workspace, Path(args.output))
    summary = suite.run(api_host=args.host, api_port=args.port)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
