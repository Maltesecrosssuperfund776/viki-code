from __future__ import annotations

import ast
from pathlib import Path


class ASTEditError(ValueError):
    pass


class ASTEditEngine:
    def replace_function_source(self, source: str, function_name: str, replacement: str) -> str:
        tree = ast.parse(source)
        target = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                target = node
                break
        if target is None:
            raise ASTEditError(f"function '{function_name}' not found")
        if not hasattr(target, "lineno") or not hasattr(target, "end_lineno"):
            raise ASTEditError("python runtime lacks end_lineno support")
        lines = source.splitlines(keepends=True)
        start = target.lineno - 1
        end = target.end_lineno
        indent = len(lines[start]) - len(lines[start].lstrip())
        repl = replacement.strip("\n") + "\n"
        if indent:
            repl = "\n".join((" " * indent + line if line.strip() else line) for line in repl.splitlines()) + "\n"
        lines[start:end] = [repl]
        return "".join(lines)

    def replace_function_in_file(self, path: str | Path, function_name: str, replacement: str) -> None:
        file_path = Path(path)
        updated = self.replace_function_source(file_path.read_text(encoding="utf-8"), function_name, replacement)
        file_path.write_text(updated, encoding="utf-8")
