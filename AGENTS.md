Repo rules for VIKI Code

- No placeholder implementations.
- No fake benchmark claims.
- No mocked superiority claims presented as real.
- Every new feature must include tests.
- Any command mentioned in docs must be runnable.
- Prefer explicit diffs and reversible changes.
- Preserve rollback/revert paths for risky changes.
- Save machine-readable benchmark outputs.
- Save redacted live-run outputs.
- If a benchmark cannot fully run in this environment, implement the harness, run the feasible subset, and state the exact blocker.
- Ask for the temporary API key only when the code is ready for real live execution.
- Use secrets only via environment variables.
- Never persist secrets to repo files, docs, logs, artifacts, screenshots, or reports.
- Keep final reporting proof-based and concise.
- Fix weak architecture instead of preserving it for compatibility by default.
- Remove stale docs, stale placeholders, and dead commands.
Final continuation rule:
- Continue from the current validated repo state.
- Do not restart the project from zero.
- Read existing proof artifacts first, then patch only what is still left.
- Rerun live validation on the updated code before packaging.
- Package only from the final updated validated state.
Final hardening rules

- Continue only from the current 4.1.3 validated state.
- Do not restart from zero.
- Improve speed, breadth, robustness, installability, and public release quality.
- Validate like a real user from command prompt or equivalent shell, not only internal module calls.
- Run repeated generic-prompt live tasks, not just file-scoped prompts.
- Run at least one bigger realistic task.
- Validate container isolation if possible; if blocked, prove the blocker.
- Remove stale/noisy comments, but keep necessary legal and high-value explanatory comments.
- Package only from the final validated state.
- Do not overclaim leadership without proof.

Public release README rules

- Continue only from the current 4.1.4 state.
- Do not restart engineering work unless required for public-facing correctness.
- Keep README marketing strong but evidence-backed.
- Do not claim world-best or category leadership without proof.
- Create clean SVG branding assets that render on GitHub.
- Prefer premium, serious product framing over hype spam.
- Publish to GitHub only if auth and remote details are truly available.
- If GitHub publishing is blocked, ask once for the exact missing details.