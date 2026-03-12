from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def generate_stress_repos(root: str | Path) -> Dict[str, str]:
    destination = Path(root).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    repos = {
        "monorepo": destination / "monorepo",
        "polyglot": destination / "polyglot",
        "migration": destination / "migration_repo",
        "flaky": destination / "flaky_repo",
        "bug_localization": destination / "bug_localization_repo",
        "dependency_conflict": destination / "dependency_conflict_repo",
        "large_test_matrix": destination / "large_test_matrix_repo",
    }

    _write(
        repos["monorepo"] / "README.md",
        "# Monorepo Stress Repo\n\nThis repo simulates a Python service plus shared packages.\n",
    )
    _write(
        repos["monorepo"] / "apps" / "api" / "service.py",
        "from packages.shared.auth import normalize_user\n\n\ndef handler(name: str) -> str:\n    return normalize_user(name)\n",
    )
    _write(
        repos["monorepo"] / "packages" / "shared" / "auth.py",
        "def normalize_user(name: str) -> str:\n    return name.strip().lower()\n",
    )
    _write(
        repos["monorepo"] / "tests" / "test_service.py",
        "from apps.api.service import handler\n\n\ndef test_handler():\n    assert handler(' Alice ') == 'alice'\n",
    )

    _write(repos["polyglot"] / "README.md", "# Polyglot Stress Repo\n")
    _write(repos["polyglot"] / "src" / "main.py", "def add(a: int, b: int) -> int:\n    return a + b\n")
    _write(repos["polyglot"] / "web" / "app.ts", "export function greet(name: string) { return `hello ${name}`; }\n")
    _write(repos["polyglot"] / "go" / "cmd" / "server" / "main.go", "package main\n\nfunc main() {}\n")

    _write(repos["migration"] / "README.md", "# Migration Repo\n\nMigrate callers from `legacy_sum` to `sum_numbers`.\n")
    _write(repos["migration"] / "legacy.py", "def legacy_sum(values):\n    return sum(values)\n")
    _write(repos["migration"] / "new_api.py", "def sum_numbers(values):\n    return sum(values)\n")
    _write(
        repos["migration"] / "consumer.py",
        "from legacy import legacy_sum\n\n\ndef total(values):\n    return legacy_sum(values)\n",
    )

    _write(repos["flaky"] / "README.md", "# Flaky Repo\n")
    _write(
        repos["flaky"] / "tests" / "test_flaky.py",
        "import os\n\n\ndef test_flaky_example():\n    assert os.getenv('VIKI_FLAKY_MODE', 'stable') == 'stable'\n",
    )

    _write(repos["bug_localization"] / "README.md", "# Bug Localization Repo\n")
    _write(
        repos["bug_localization"] / "app" / "calculator.py",
        "def multiply(a: int, b: int) -> int:\n    return a + b\n",
    )
    _write(
        repos["bug_localization"] / "tests" / "test_calculator.py",
        "from app.calculator import multiply\n\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n",
    )

    _write(repos["dependency_conflict"] / "README.md", "# Dependency Conflict Repo\n")
    _write(repos["dependency_conflict"] / "requirements.txt", "requests==2.28.0\nurllib3==2.3.0\n")
    _write(repos["dependency_conflict"] / "constraints.txt", "urllib3<2\n")

    _write(repos["large_test_matrix"] / "README.md", "# Large Test Matrix Repo\n")
    for index in range(1, 9):
        _write(
            repos["large_test_matrix"] / "pkg" / f"feature_{index}.py",
            f"def feature_{index}(value):\n    return value + {index}\n",
        )
        _write(
            repos["large_test_matrix"] / "tests" / f"test_feature_{index}.py",
            f"from pkg.feature_{index} import feature_{index}\n\n\ndef test_feature_{index}():\n    assert feature_{index}(1) == {index + 1}\n",
        )

    manifest = {name: str(path) for name, path in repos.items()}
    _write(destination / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest
