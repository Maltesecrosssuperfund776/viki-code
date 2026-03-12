# Contributing to VIKI Code

Thanks for contributing to VIKI Code.

## What We Optimize For

- real implementation instead of placeholders
- honest proof instead of aspirational claims
- reversible changes for risky operations
- docs and commands that match reality

## Development Flow

1. Create a focused branch.
2. Make the smallest coherent change that solves the problem well.
3. Run the relevant validation before opening a pull request.
4. Update docs or proof artifacts when public behavior changes.

## Suggested Validation

```bash
python -m pytest
python -m build
python scripts/install.py --path . --dry-run
```

When a change affects live execution, repo intelligence, install flow, or public proof, include the exact commands you ran and the outcome.

## Pull Requests

Use the pull request template and include:

- a concise summary
- verification steps
- risk notes
- rollback notes when relevant

## Ground Rules

- do not add fake benchmark claims
- do not add dead commands or placeholder examples
- do not persist secrets in source, logs, or artifacts
- prefer clear, maintainable source over noisy cleverness
