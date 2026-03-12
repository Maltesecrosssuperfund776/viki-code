from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ..config import settings


@dataclass
class SymbolRecord:
    name: str
    kind: str
    path: str
    line: int
    container: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class RepoFileSummary:
    path: str
    size: int
    extension: str
    language: str
    symbols: List[str]
    imports: List[str] | None = None
    summary: str = ""
    package: str = ""
    headings: List[str] = field(default_factory=list)
    symbol_table: List[Dict[str, object]] = field(default_factory=list)
    lines: int = 0
    fingerprint: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class RepoIndex:
    """Incremental repo map tuned for large monorepos and repair workflows."""

    CACHE_VERSION = 2
    IGNORED_DIRS = {
        ".git",
        settings.workspace_dir,
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".next",
        ".turbo",
        ".mypy_cache",
        ".pytest_cache",
        "__pycache__",
        ".venv",
        "venv",
    }
    TEXT_EXTENSIONS = {
        ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".c", ".cc", ".cpp", ".h", ".hpp",
        ".cs", ".rb", ".php", ".swift", ".scala", ".sql", ".sh", ".bash", ".zsh", ".ps1", ".toml", ".yaml", ".yml", ".json",
        ".ini", ".cfg", ".md", ".txt", ".rst", ".html", ".css", ".env", ".properties",
    }
    LANGUAGE_MAP = {
        ".py": "python", ".pyi": "python",
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
        ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
        ".cs": "csharp", ".rb": "ruby", ".php": "php", ".swift": "swift", ".scala": "scala",
        ".sql": "sql", ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".ps1": "powershell",
        ".toml": "config", ".yaml": "config", ".yml": "config", ".json": "config", ".ini": "config", ".cfg": "config",
        ".md": "docs", ".txt": "docs", ".rst": "docs", ".html": "web", ".css": "web", ".env": "config", ".properties": "config",
    }
    INSTRUCTION_FILES = [
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "CONTRIBUTING.md",
        "pyproject.toml",
        "package.json",
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
    ]

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        self.cache_path = self.workspace / settings.workspace_dir / "repo_index.json"
        self._files: List[RepoFileSummary] | None = None
        self._profile: Dict[str, object] | None = None
        self._imports_index: Dict[str, List[str]] | None = None
        self._forward_import_index: Dict[str, List[str]] | None = None
        self._tests_index: Dict[str, List[str]] | None = None
        self._symbol_index: List[Dict[str, object]] | None = None
        self._package_summaries: List[Dict[str, object]] | None = None

    def _repo_rel(self, path: Path) -> str:
        return path.relative_to(self.workspace).as_posix()

    def build(self, force: bool = False) -> List[RepoFileSummary]:
        if self._files is not None and not force:
            return self._files

        cached_payload = self._load_cache() if not force else {}
        cached_files = {item["path"]: item for item in cached_payload.get("files", [])}
        cached_meta = cached_payload.get("file_meta", {})

        files: List[RepoFileSummary] = []
        file_meta: Dict[str, Dict[str, int]] = {}
        for path in self._iter_files():
            rel = self._repo_rel(path)
            stat = path.stat()
            meta = {"size": int(stat.st_size), "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))}
            file_meta[rel] = meta
            if cached_meta.get(rel) == meta and rel in cached_files:
                files.append(RepoFileSummary(**cached_files[rel]))
                continue
            files.append(self._summarize_file(path, rel, meta))

        self._files = sorted(files, key=lambda item: item.path)
        self._forward_import_index, self._imports_index = self._build_import_indices(self._files)
        self._tests_index = self._build_tests_index(self._files)
        self._symbol_index = self._build_symbol_index(self._files)
        self._package_summaries = self._build_package_summaries(self._files)
        self._profile = self._compute_profile(self._files)

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(
                {
                    "version": self.CACHE_VERSION,
                    "profile": self._profile,
                    "file_meta": file_meta,
                    "files": [item.to_dict() for item in self._files],
                    "imports_index": self._imports_index,
                    "forward_import_index": self._forward_import_index,
                    "tests_index": self._tests_index,
                    "symbols": self._symbol_index,
                    "packages": self._package_summaries,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return self._files

    def _load_cache(self) -> Dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if int(payload.get("version", 0) or 0) != self.CACHE_VERSION:
            return {}
        self._profile = payload.get("profile") or None
        self._imports_index = payload.get("imports_index") or None
        self._forward_import_index = payload.get("forward_import_index") or None
        self._tests_index = payload.get("tests_index") or None
        self._symbol_index = payload.get("symbols") or None
        self._package_summaries = payload.get("packages") or None
        return payload

    def profile(self) -> Dict[str, object]:
        files = self.build()
        return dict(self._profile or self._compute_profile(files))

    def instructions(self, limit: int = 4, max_chars_per_file: int = 1800) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        seen: set[str] = set()
        for name in self.INSTRUCTION_FILES:
            matches: List[Path] = []
            if name == "README.md":
                root_readme = self.workspace / name
                if root_readme.exists():
                    matches.append(root_readme)
                docs_dir = self.workspace / "docs"
                if docs_dir.exists():
                    matches.extend(sorted(docs_dir.rglob(name)))
            else:
                direct = self.workspace / name
                if direct.exists():
                    matches.append(direct)
                matches.extend(sorted(path for path in self.workspace.rglob(name) if settings.workspace_dir not in path.parts))
            for path in matches:
                if not path.exists() or not path.is_file():
                    continue
                rel = self._repo_rel(path)
                if rel in seen:
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                results.append({"path": rel, "preview": content[:max_chars_per_file]})
                seen.add(rel)
                if len(results) >= limit:
                    return results
        return results

    def package_summaries(self, limit: int = 12) -> List[Dict[str, object]]:
        self.build()
        return [dict(item) for item in (self._package_summaries or [])[:limit]]

    def symbols(self, query: str = "", paths: Iterable[str] | None = None, limit: int = 25) -> List[Dict[str, object]]:
        self.build()
        wanted_paths = {str(item).replace("\\", "/") for item in (paths or []) if item}
        tokens = self._tokens(query)
        results: List[tuple[float, Dict[str, object]]] = []
        for symbol in self._symbol_index or []:
            path = str(symbol.get("path", ""))
            if wanted_paths and path not in wanted_paths:
                continue
            score = 0.0
            if not tokens:
                score = 1.0
            else:
                score += len(tokens & self._tokens(str(symbol.get("name", "")))) * 12.0
                score += len(tokens & self._tokens(path)) * 6.0
                score += len(tokens & self._tokens(str(symbol.get("container", "")))) * 4.0
            if score > 0:
                results.append((score, symbol))
        results.sort(key=lambda item: (-item[0], str(item[1].get("path")), str(item[1].get("name"))))
        return [{**item, "score": round(score, 2)} for score, item in results[:limit]]

    def focus(self, query: str, target_files: Iterable[str] | None = None, limit: int = 25) -> List[Dict[str, object]]:
        target_files = {str(item).replace("\\", "/") for item in (target_files or []) if item}
        files = self.build()
        tokens = self._tokens(query)
        reverse_imports = self._imports_index or {}
        forward_imports = self._forward_import_index or {}
        tests_index = self._tests_index or {}

        expanded_targets = set(target_files)
        for target in list(target_files):
            expanded_targets.update(reverse_imports.get(target, []))
            expanded_targets.update(forward_imports.get(target, []))
            expanded_targets.update(tests_index.get(target, []))
            expanded_targets.update(self._same_package_neighbors(target, limit=6))

        scored: List[tuple[float, RepoFileSummary]] = []
        for item in files:
            score = 0.0
            path_tokens = self._tokens(item.path)
            basename_tokens = self._tokens(Path(item.path).name)
            symbol_tokens = {token for symbol in item.symbols for token in self._tokens(symbol)}
            import_tokens = {token for module in (item.imports or []) for token in self._tokens(module)}
            summary_tokens = self._tokens(item.summary)
            heading_tokens = {token for heading in item.headings for token in self._tokens(heading)}
            package_tokens = self._tokens(item.package)

            if item.path in expanded_targets:
                score += 120.0 if item.path in target_files else 28.0
            score += len(tokens & path_tokens) * 9.0
            score += len(tokens & basename_tokens) * 11.0
            score += len(tokens & symbol_tokens) * 7.0
            score += len(tokens & import_tokens) * 4.0
            score += len(tokens & summary_tokens) * 5.0
            score += len(tokens & heading_tokens) * 3.0
            score += len(tokens & package_tokens) * 2.0

            if any(token in item.path.lower() for token in ["test", "spec"]) and any(token in tokens for token in {"bug", "fix", "test", "pytest", "flaky", "regression"}):
                score += 4.0
            if item.language == "docs" and any(token in tokens for token in {"readme", "docs", "documentation", "instructions"}):
                score += 6.0
            if item.language in {"python", "typescript", "javascript", "go", "rust"}:
                score += 1.0
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda pair: (-pair[0], pair[1].path))
        return [
            {
                "path": item.path,
                "language": item.language,
                "size": item.size,
                "package": item.package,
                "summary": item.summary,
                "symbols": item.symbols[:8],
                "imports": (item.imports or [])[:8],
                "score": round(score, 2),
            }
            for score, item in scored[:limit]
        ]

    def dependency_neighbors(self, target_files: Iterable[str], limit: int = 20) -> List[str]:
        self.build()
        neighbors: List[str] = []
        seen = {str(item).replace("\\", "/") for item in target_files if item}
        reverse_imports = self._imports_index or {}
        forward_imports = self._forward_import_index or {}
        for path in list(seen):
            for item in reverse_imports.get(path, []) + forward_imports.get(path, []) + self._same_package_neighbors(path, limit=8):
                if item not in seen:
                    neighbors.append(item)
                    seen.add(item)
                    if len(neighbors) >= limit:
                        return neighbors
        return neighbors

    def impact_report(self, changed_files: Iterable[str], limit: int = 20) -> Dict[str, object]:
        changed = [str(item).replace("\\", "/") for item in changed_files if item]
        neighbors = self.dependency_neighbors(changed, limit=limit)
        tests = self.test_targets(changed + neighbors, limit=max(8, limit // 2))
        affected_packages = sorted({item["package"] for item in self.focus(" ".join(changed), target_files=changed, limit=limit) if item.get("package")})
        symbols = self.symbols(paths=changed + neighbors, limit=limit)
        return {
            "changed_files": changed,
            "neighbors": neighbors,
            "tests": tests,
            "packages": affected_packages[:limit],
            "symbols": symbols,
        }

    def context_pack(self, query: str, target_files: Iterable[str] | None = None, limit: int = 12) -> Dict[str, object]:
        target_files = [str(item).replace("\\", "/") for item in (target_files or []) if item]
        focus = self.focus(query, target_files=target_files, limit=limit)
        focus_paths = [item["path"] for item in focus[: max(6, limit // 2)]]
        impact = self.impact_report(target_files or focus_paths, limit=limit)
        return {
            "profile": self.profile(),
            "instructions": self.instructions(limit=4),
            "focus": focus,
            "impact": impact,
            "symbols": self.symbols(query, paths=focus_paths + impact.get("neighbors", []), limit=limit),
            "packages": self.package_summaries(limit=min(limit, 8)),
            "snippets": self.snippets(focus_paths + list(impact.get("neighbors", []))[:4]),
        }

    def test_targets(self, changed_files: Iterable[str], limit: int = 8) -> List[str]:
        self.build()
        tests_index = self._tests_index or {}
        results: List[str] = []
        seen: set[str] = set()
        changed = [str(item).replace("\\", "/") for item in changed_files if item]
        changed_symbols = {symbol["name"] for symbol in self.symbols(paths=changed, limit=50)}
        for relative in changed:
            for path in tests_index.get(relative, []):
                if path not in seen:
                    results.append(path)
                    seen.add(path)
                    if len(results) >= limit:
                        return results
            changed_name = Path(relative).stem.replace("test_", "")
            for file in self._files or []:
                if file.path in seen or not file.path.startswith("tests/"):
                    continue
                test_tokens = self._tokens(file.path)
                if changed_name and changed_name in Path(file.path).stem:
                    results.append(file.path)
                    seen.add(file.path)
                elif changed_symbols and changed_symbols & {symbol["name"] for symbol in file.symbol_table if isinstance(symbol, dict)}:
                    results.append(file.path)
                    seen.add(file.path)
                elif self._tokens(changed_name) & test_tokens:
                    results.append(file.path)
                    seen.add(file.path)
                if len(results) >= limit:
                    return results
        return results

    def snippets(self, paths: Iterable[str], max_chars_per_file: int = 900) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for relative in paths:
            target = (self.workspace / str(relative).replace("\\", "/")).resolve()
            if not target.exists() or not target.is_file():
                continue
            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            results.append({"path": str(Path(relative)).replace("\\", "/"), "preview": content[:max_chars_per_file]})
        return results

    def _iter_files(self) -> Iterable[Path]:
        for path in self.workspace.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.workspace)
            if any(part in self.IGNORED_DIRS for part in rel.parts):
                continue
            if path.suffix.lower() not in self.TEXT_EXTENSIONS and path.stat().st_size > 256_000:
                continue
            yield path

    def _summarize_file(self, path: Path, rel: str, meta: Dict[str, int]) -> RepoFileSummary:
        suffix = path.suffix.lower()
        language = self.LANGUAGE_MAP.get(suffix, "other")
        content = path.read_text(encoding="utf-8", errors="ignore") if suffix in self.TEXT_EXTENSIONS or meta["size"] <= 512_000 else ""
        lines = len(content.splitlines()) if content else 0
        package = self._package_name(rel)
        headings = self._extract_headings(content, language)
        symbols: List[str] = []
        symbol_table: List[Dict[str, object]] = []
        imports: List[str] = []
        summary = ""

        if language == "python" and meta["size"] <= 768_000:
            symbols, symbol_table, imports, summary = self._summarize_python(content, rel)
        elif language in {"javascript", "typescript"} and meta["size"] <= 768_000:
            symbols, symbol_table, imports, summary = self._summarize_js_like(content, rel, language)
        else:
            summary = self._infer_summary(rel, language, content, symbols, headings)

        if not summary:
            summary = self._infer_summary(rel, language, content, symbols, headings)

        return RepoFileSummary(
            path=rel,
            size=meta["size"],
            extension=suffix,
            language=language,
            symbols=symbols[:24],
            imports=imports[:32],
            summary=summary[:240],
            package=package,
            headings=headings[:8],
            symbol_table=symbol_table[:48],
            lines=lines,
            fingerprint=f"{meta['size']}:{meta['mtime_ns']}",
        )

    def _summarize_python(self, content: str, rel: str) -> tuple[List[str], List[Dict[str, object]], List[str], str]:
        symbols: List[str] = []
        symbol_table: List[Dict[str, object]] = []
        imports: List[str] = []
        summary = ""
        try:
            tree = ast.parse(content)
        except Exception:
            return symbols, symbol_table, imports, summary

        module_doc = ast.get_docstring(tree) or ""
        if module_doc:
            summary = module_doc.strip().splitlines()[0]

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                symbols.append(node.name)
                symbol_table.append(SymbolRecord(node.name, "class", rel, getattr(node, "lineno", 1)).to_dict())
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbol_table.append(SymbolRecord(child.name, "method", rel, getattr(child, "lineno", 1), container=node.name).to_dict())
            elif isinstance(node, ast.FunctionDef):
                symbols.append(node.name)
                symbol_table.append(SymbolRecord(node.name, "function", rel, getattr(node, "lineno", 1)).to_dict())
            elif isinstance(node, ast.AsyncFunctionDef):
                symbols.append(node.name)
                symbol_table.append(SymbolRecord(node.name, "async_function", rel, getattr(node, "lineno", 1)).to_dict())

        imports = self._extract_python_imports(tree, rel)
        if not summary:
            kinds = []
            if any(item["kind"] == "class" for item in symbol_table):
                kinds.append("classes")
            if any(item["kind"] in {"function", "async_function"} for item in symbol_table):
                kinds.append("functions")
            if kinds:
                summary = f"Python module defining {', '.join(kinds)}: {', '.join(symbols[:4])}"
        return symbols, symbol_table, imports, summary

    def _summarize_js_like(self, content: str, rel: str, language: str) -> tuple[List[str], List[Dict[str, object]], List[str], str]:
        symbols: List[str] = []
        symbol_table: List[Dict[str, object]] = []
        imports: List[str] = []
        summary = ""
        import_pattern = re.compile(r"""(?:import\s+.+?\s+from\s+['"]([^'"]+)['"])|(?:require\(\s*['"]([^'"]+)['"]\s*\))""")
        for match in import_pattern.finditer(content):
            imports.extend(part for part in match.groups() if part)
        symbol_patterns = [
            (re.compile(r"export\s+class\s+([A-Za-z_][A-Za-z0-9_]*)"), "class"),
            (re.compile(r"class\s+([A-Za-z_][A-Za-z0-9_]*)"), "class"),
            (re.compile(r"export\s+function\s+([A-Za-z_][A-Za-z0-9_]*)"), "function"),
            (re.compile(r"function\s+([A-Za-z_][A-Za-z0-9_]*)"), "function"),
            (re.compile(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\("), "const"),
        ]
        for pattern, kind in symbol_patterns:
            for match in pattern.finditer(content):
                name = match.group(1)
                if name in symbols:
                    continue
                symbols.append(name)
                line = content.count("\n", 0, match.start()) + 1
                symbol_table.append(SymbolRecord(name, kind, rel, line).to_dict())
        comment = self._first_comment_line(content)
        if comment:
            summary = comment
        elif symbols:
            summary = f"{language.title()} module defining {', '.join(symbols[:4])}"
        return symbols, symbol_table, imports, summary

    def _extract_python_imports(self, tree: ast.AST, rel: str) -> List[str]:
        imports: List[str] = []
        rel_parts = Path(rel).with_suffix("").parts
        current_pkg = list(rel_parts[:-1])
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    base = current_pkg[: max(0, len(current_pkg) - node.level + 1)]
                    resolved = ".".join(part for part in base + ([module] if module else []) if part)
                    if resolved:
                        imports.append(resolved)
                elif module:
                    imports.append(module)
        return imports

    def _build_import_indices(self, files: List[RepoFileSummary]) -> tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        module_to_path: Dict[str, str] = {}
        for item in files:
            if item.language != "python":
                continue
            module = ".".join(Path(item.path).with_suffix("").parts)
            module_to_path[module] = item.path

        forward: Dict[str, List[str]] = {item.path: [] for item in files}
        reverse: Dict[str, List[str]] = {item.path: [] for item in files}
        for item in files:
            for mod in item.imports or []:
                candidates = [mod]
                parts = mod.split(".")
                while len(parts) > 1:
                    parts = parts[:-1]
                    candidates.append(".".join(parts))
                for candidate in candidates:
                    target = module_to_path.get(candidate)
                    if target and target != item.path:
                        forward.setdefault(item.path, []).append(target)
                        reverse.setdefault(target, []).append(item.path)
                        break
        return (
            {key: sorted(set(values)) for key, values in forward.items() if values},
            {key: sorted(set(values)) for key, values in reverse.items() if values},
        )

    def _build_tests_index(self, files: List[RepoFileSummary]) -> Dict[str, List[str]]:
        tests = [item for item in files if item.path.startswith("tests/") or Path(item.path).name.startswith("test_")]
        mapping: Dict[str, List[str]] = {item.path: [] for item in files}
        for item in files:
            if item in tests:
                continue
            stem = Path(item.path).stem
            normalized = stem.replace("__init__", "").strip("_")
            guesses = [f"tests/test_{normalized}.py", f"tests/{normalized}_test.py"] if normalized else []
            linked = [path.path for path in tests if path.path in guesses or normalized and normalized in Path(path.path).stem]
            same_package = [path.path for path in tests if item.package and path.path.startswith(f"tests/{item.package.split('/', 1)[0]}")]
            values = sorted(dict.fromkeys(linked + same_package))[:10]
            if values:
                mapping[item.path] = values
        return {key: value for key, value in mapping.items() if value}

    def _build_symbol_index(self, files: List[RepoFileSummary]) -> List[Dict[str, object]]:
        symbols: List[Dict[str, object]] = []
        for item in files:
            for symbol in item.symbol_table:
                symbols.append({**symbol, "language": item.language, "package": item.package})
        return symbols

    def _build_package_summaries(self, files: List[RepoFileSummary]) -> List[Dict[str, object]]:
        grouped: Dict[str, List[RepoFileSummary]] = defaultdict(list)
        for item in files:
            grouped[item.package or "."].append(item)
        packages: List[Dict[str, object]] = []
        for package, members in grouped.items():
            languages: Dict[str, int] = defaultdict(int)
            symbol_names: List[str] = []
            summaries: List[str] = []
            for member in members:
                languages[member.language] += 1
                symbol_names.extend(member.symbols[:3])
                if member.summary:
                    summaries.append(member.summary)
            packages.append(
                {
                    "package": package,
                    "file_count": len(members),
                    "languages": dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))[:6]),
                    "top_symbols": list(dict.fromkeys(symbol_names))[:8],
                    "summary": summaries[0] if summaries else f"{package} package with {len(members)} files",
                }
            )
        packages.sort(key=lambda item: (-int(item["file_count"]), str(item["package"])))
        return packages

    def _compute_profile(self, files: List[RepoFileSummary]) -> Dict[str, object]:
        by_language: Dict[str, int] = {}
        for item in files:
            by_language[item.language] = by_language.get(item.language, 0) + 1
        instructions = [entry["path"] for entry in self.instructions(limit=6, max_chars_per_file=200)]
        return {
            "root": str(self.workspace),
            "file_count": len(files),
            "symbol_count": len(self._symbol_index or []),
            "package_count": len(self._package_summaries or []),
            "languages": dict(sorted(by_language.items(), key=lambda pair: (-pair[1], pair[0]))[:12]),
            "large_repo": len(files) >= settings.route_large_repo_threshold,
            "instruction_files": instructions,
        }

    def _package_name(self, rel: str) -> str:
        parent = Path(rel).parent
        if str(parent) in {"", "."}:
            return "."
        return parent.as_posix()

    def _same_package_neighbors(self, rel: str, limit: int = 8) -> List[str]:
        rel = rel.replace("\\", "/")
        package = self._package_name(rel)
        if package == ".":
            return []
        neighbors = [item.path for item in self._files or [] if item.package == package and item.path != rel]
        return neighbors[:limit]

    def _extract_headings(self, content: str, language: str) -> List[str]:
        headings: List[str] = []
        if language == "docs":
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    headings.append(stripped.lstrip("#").strip())
        elif language == "config":
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    headings.append(stripped.strip("[]"))
        return headings

    def _first_comment_line(self, content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("//"):
                return stripped.lstrip("/").strip()
            if stripped.startswith("/*") and stripped.endswith("*/"):
                return stripped.strip("/* ").strip()
        return ""

    def _infer_summary(self, rel: str, language: str, content: str, symbols: List[str], headings: List[str]) -> str:
        if headings:
            return headings[0]
        if symbols:
            return f"{language.title()} file with symbols {', '.join(symbols[:4])}"
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:160]
        return f"{language.title()} file {Path(rel).name}"

    def _tokens(self, text: str) -> set[str]:
        cleaned = []
        for char in text.lower():
            cleaned.append(char if char.isalnum() else " ")
        return {token for token in "".join(cleaned).split() if len(token) >= 2}
