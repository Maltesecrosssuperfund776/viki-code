# Security Policy

## Supported Version

The current supported public release line is `4.1.x`.

## Reporting A Vulnerability

If you discover a security issue in VIKI Code, please report it privately before opening a public issue.

Include:

- a concise description of the issue
- affected version or commit
- impact and reproduction steps
- any logs or traces needed to understand the problem

Please do not include secrets, API keys, or private credentials in your report.

## Safety Posture

VIKI Code is designed around governed execution:

- approval-aware task flow
- isolated task worktrees
- redacted logs and proof artifacts
- rollback and patch export paths

That design reduces operator risk, but it does not remove the need for normal secure deployment and credential hygiene.
