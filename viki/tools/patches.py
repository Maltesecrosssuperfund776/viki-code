from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


class PatchApplyError(ValueError):
    pass


@dataclass
class HunkLine:
    op: str
    text: str


@dataclass
class Hunk:
    src_start: int
    src_len: int
    dst_start: int
    dst_len: int
    lines: List[HunkLine] = field(default_factory=list)


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchEngine:
    """Apply unified diffs and search/replace patches without full overwrites."""

    def apply_patch(self, original: str, patch_text: str) -> str:
        hunks = self._parse_unified_diff(patch_text)
        if not hunks:
            raise PatchApplyError("no hunks found in patch")
        src = original.splitlines(keepends=True)
        result: List[str] = []
        cursor = 0

        for hunk in hunks:
            start_index = max(hunk.src_start - 1, 0)
            if start_index < cursor:
                raise PatchApplyError("overlapping hunks")
            result.extend(src[cursor:start_index])
            src_index = start_index
            for entry in hunk.lines:
                if entry.op == " ":
                    if src_index >= len(src):
                        raise PatchApplyError("context extends past end of file")
                    if src[src_index].rstrip("\n") != entry.text.rstrip("\n"):
                        raise PatchApplyError(
                            f"context mismatch at source line {src_index + 1}: expected {entry.text!r} got {src[src_index]!r}"
                        )
                    result.append(src[src_index])
                    src_index += 1
                elif entry.op == "-":
                    if src_index >= len(src):
                        raise PatchApplyError("deletion extends past end of file")
                    if src[src_index].rstrip("\n") != entry.text.rstrip("\n"):
                        raise PatchApplyError(
                            f"delete mismatch at source line {src_index + 1}: expected {entry.text!r} got {src[src_index]!r}"
                        )
                    src_index += 1
                elif entry.op == "+":
                    result.append(entry.text)
                else:
                    raise PatchApplyError(f"unsupported hunk op: {entry.op}")
            cursor = src_index

        result.extend(src[cursor:])
        return "".join(result)

    def replace_block(self, original: str, old: str, new: str, count: int = 1) -> str:
        if old not in original:
            raise PatchApplyError("target block not found")
        replaced = original.replace(old, new, count)
        if replaced == original:
            raise PatchApplyError("replace produced no changes")
        return replaced

    def _parse_unified_diff(self, patch_text: str) -> List[Hunk]:
        lines = patch_text.splitlines(keepends=True)
        hunks: List[Hunk] = []
        current: Hunk | None = None
        for line in lines:
            if line.startswith(("---", "+++", "diff --git", "index ")):
                continue
            if line.startswith("@@"):
                match = _HUNK_RE.match(line.strip())
                if not match:
                    raise PatchApplyError(f"invalid hunk header: {line.strip()}")
                current = Hunk(
                    src_start=int(match.group(1)),
                    src_len=int(match.group(2) or "1"),
                    dst_start=int(match.group(3)),
                    dst_len=int(match.group(4) or "1"),
                )
                hunks.append(current)
                continue
            if current is None:
                continue
            if line.startswith("\\"):
                continue
            if not line:
                current.lines.append(HunkLine(" ", line))
                continue
            op = line[0]
            if op not in {" ", "+", "-"}:
                raise PatchApplyError(f"invalid diff line: {line!r}")
            current.lines.append(HunkLine(op, line[1:]))
        return hunks
