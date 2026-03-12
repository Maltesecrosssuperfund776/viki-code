from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List


class MergeResolver:
    """Resolve concurrent file operations from multiple swarms.

    The resolver keeps a diff-first summary so higher layers can detect whether
    swarm parallelism is helping or creating conflict amplification.
    """

    WRITE_MODES = {"write", "patch", "replace_block", "ast_replace_function", "append", "json_merge", "delete"}

    def combine_operations(self, batches: Iterable[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        by_path: dict[str, list[Dict[str, Any]]] = defaultdict(list)
        passthrough: List[Dict[str, Any]] = []
        for batch_index, batch in enumerate(batches):
            for op_index, op in enumerate(batch):
                enriched = {**op, "_batch_index": batch_index, "_op_index": op_index}
                path = op.get("path")
                if not path:
                    passthrough.append(enriched)
                    continue
                by_path[path].append(enriched)
        merged = list(passthrough)
        for path, ops in by_path.items():
            if len(ops) == 1:
                merged.append(self._strip_meta(ops[0]))
                continue
            conflicts = self._conflicts_for_path(ops)
            last_write = next((op for op in reversed(ops) if op.get("mode") in self.WRITE_MODES), ops[-1])
            merged.append(
                self._strip_meta(
                    {
                        **last_write,
                        "merge_notes": [self._describe_op(op) for op in ops],
                        "merge_conflicts": conflicts,
                        "parallel_touch_count": len(ops),
                    }
                )
            )
        return merged

    def _conflicts_for_path(self, ops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        seen_symbols: dict[str, Dict[str, Any]] = {}
        seen_old_blocks: dict[str, Dict[str, Any]] = {}
        seen_modes: dict[str, int] = {}
        for op in ops:
            mode = str(op.get("mode", "write"))
            seen_modes[mode] = seen_modes.get(mode, 0) + 1
            symbol = op.get("symbol")
            if symbol:
                if symbol in seen_symbols:
                    conflicts.append({"type": "symbol", "symbol": symbol, "reason": "multiple swarms edit same symbol"})
                seen_symbols[str(symbol)] = op
            old_block = op.get("old")
            if old_block:
                key = str(old_block)[:120]
                if key in seen_old_blocks:
                    conflicts.append({"type": "block", "reason": "multiple replace_block operations touch similar content"})
                seen_old_blocks[key] = op
        if seen_modes.get("delete") and len(ops) > 1:
            conflicts.append({"type": "delete_vs_edit", "reason": "delete overlaps with another write operation"})
        return conflicts

    def _describe_op(self, op: Dict[str, Any]) -> str:
        parts = [str(op.get("mode", "write"))]
        if op.get("symbol"):
            parts.append(f"symbol={op['symbol']}")
        summary = op.get("summary")
        if summary:
            parts.append(str(summary))
        return " | ".join(parts)

    def _strip_meta(self, op: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in op.items() if not k.startswith("_")}
