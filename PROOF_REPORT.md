# VIKI Code 4.1.4 Proof Report

## Scope

This report covers the final 4.1.4 finish-and-harden pass on top of the 4.1.3 baseline. The work stayed targeted: improve generic live reliability, expand proof breadth, validate human install and isolated execution, clean packaging, and rebuild the final public release artifacts from the updated code.

## Major changes in this pass

- Used the coding model for localized refactors and retried malformed structured responses before failing a candidate.
- Reduced repeated work by deduping validation/security commands and tightening small-task candidate fanout.
- Added deterministic runbook generation for docs-only tasks that ask what changed and what to run.
- Improved migration localization so caller files are preferred over API definition files for vague migration prompts.
- Added Linux `python` -> `python3` fallback in the command executor for environments where only `python3` exists.
- Strengthened isolation validation with safe WSL env forwarding and force-reinstall behavior for the wheel.
- Cleaned the Python package manifest so historical proof artifact trees are not bundled into the sdist.

## Exact commands run

Targeted regression checks:

```bash
python -m pytest tests/test_worldclass_upgrade.py::test_docs_only_tasks_ignore_generated_runtime_commands -q
python -m pytest tests/test_distribution.py::test_isolation_validator_forwards_live_provider_env -q
python -m pytest tests/test_distribution.py::test_isolation_validator_accepts_user_site_bootstrap_fallback -q
python -m pytest tests/test_smoke.py::test_prepare_command_falls_back_to_python3_when_python_missing -q
python -m pytest tests/test_worldclass_upgrade.py::test_migration_backfill_prefers_call_sites_over_api_definitions -q
python -m pytest tests/test_distribution.py -q
python -m pytest tests/test_smoke.py tests/test_distribution.py -q
python -m pytest tests/test_worldclass_upgrade.py -q
python -m pytest
```

Builds:

```bash
python -m build
python -m build
```

Human-style install validation:

```bash
python scripts/validate_human_install.py --workspace . --output LIVE_RUN_RESULTS/human_install
```

Isolation validation:

```bash
python scripts/validate_isolation.py --workspace . --output LIVE_RUN_RESULTS/isolation_validation
```

Broader live suite:

```bash
python scripts/run_public_release_live.py --workspace . --output LIVE_RUN_RESULTS/public_release --host 127.0.0.1 --port 8798
python scripts/run_public_release_live.py --workspace . --output LIVE_RUN_RESULTS/public_release --host 127.0.0.1 --port 8798
```

Benchmarks:

```bash
python -m viki.cli evals run . --dataset public --agent-name "VIKI Code Live Final 4.1.4"
python -m viki.cli evals compare .viki-workspace/benchmarks/latest_report.json --baseline codex=benchmarks/baselines/codex.json --baseline claude_code=benchmarks/baselines/claude_code.json --baseline opencode=benchmarks/baselines/opencode.json
python -m viki.cli evals publish .viki-workspace/benchmarks/latest_report.json --comparison .viki-workspace/benchmarks/latest_comparison.json
python -m viki.cli evals run . --dataset public --offline-scripted --agent-name "VIKI Code Offline Final 4.1.4"
```

Release packaging and secret check:

```bash
Compress-Archive -Path README.md,RELEASE_NOTES.md,PROOF_REPORT.md,BENCHMARK_RESULTS,LIVE_RUN_RESULTS\public_release,LIVE_RUN_RESULTS\human_install,LIVE_RUN_RESULTS\isolation_validation,scripts\run_public_release_live.py,scripts\validate_human_install.py,scripts\validate_isolation.py,dist\viki_code-4.1.4.tar.gz,dist\viki_code-4.1.4-py3-none-any.whl -DestinationPath dist\viki_code-4.1.4-public-github-release-bundle.zip -Force
rg -l -F "<exact temporary key string>" .
```

Live commands were executed only with process-scoped environment variables:

- `DASHSCOPE_API_KEY=[redacted]`
- `OPENAI_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- `DASHSCOPE_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- `VIKI_REASONING_MODEL=openai/qwen3.5-plus`
- `VIKI_CODING_MODEL=openai/qwen3-coder-next`
- `VIKI_FAST_MODEL=openai/qwen3.5-plus`

## Test results

- `python -m pytest tests/test_worldclass_upgrade.py::test_docs_only_tasks_ignore_generated_runtime_commands -q` -> `1 passed`
- `python -m pytest tests/test_distribution.py::test_isolation_validator_forwards_live_provider_env -q` -> `1 passed`
- `python -m pytest tests/test_distribution.py::test_isolation_validator_accepts_user_site_bootstrap_fallback -q` -> `1 passed`
- `python -m pytest tests/test_smoke.py::test_prepare_command_falls_back_to_python3_when_python_missing -q` -> `1 passed`
- `python -m pytest tests/test_worldclass_upgrade.py::test_migration_backfill_prefers_call_sites_over_api_definitions -q` -> `1 passed`
- `python -m pytest tests/test_distribution.py -q` -> `6 passed`
- `python -m pytest tests/test_smoke.py tests/test_distribution.py -q` -> `12 passed`
- `python -m pytest tests/test_worldclass_upgrade.py -q` -> `22 passed`
- `python -m pytest` -> `59 passed`

## Human install / run validation

Artifact:

- `LIVE_RUN_RESULTS/human_install/summary.json`

Results:

- wheel install: passed
- `viki --help`: passed
- `viki version`: passed
- `viki doctor`: passed
- `viki up --dry-run`: passed
- real installed-wheel live task: passed
- external pytest after the task: passed
- in-place update: passed
- uninstall: passed

Final summary:

- `success: true`
- `live_task_ok: true`
- `external_pytest_ok: true`
- `update_ok: true`
- `uninstall_ok: true`

## Isolation / container validation

Artifacts:

- `LIVE_RUN_RESULTS/isolation_validation/probe.json`
- `LIVE_RUN_RESULTS/isolation_validation/commands.json`
- `LIVE_RUN_RESULTS/isolation_validation/summary.json`

Runtime detection:

- Docker: unavailable
- Podman: unavailable
- WSL: available (`Ubuntu`, Python `3.12.3`)

Final isolation result:

- runtime: `wsl`
- install strategy: `user-site-bootstrap`
- live task through the isolated path: passed
- external pytest in the isolated repo: passed
- expected fix landed: passed
- overall `success: true`

## Broader live suite results

Artifacts:

- `LIVE_RUN_RESULTS/public_release/summary.json`
- `LIVE_RUN_RESULTS/public_release/api_bugfix.json`
- `LIVE_RUN_RESULTS/public_release/api_multi_agent.json`
- `LIVE_RUN_RESULTS/public_release/cli_bugfix.json`
- `LIVE_RUN_RESULTS/public_release/cli_refactor.json`
- `LIVE_RUN_RESULTS/public_release/cli_migration.json`
- `LIVE_RUN_RESULTS/public_release/cli_repo_overview.json`
- `LIVE_RUN_RESULTS/public_release/cli_matrix_bugfix.json`
- `LIVE_RUN_RESULTS/public_release/cli_change_runbook.json`
- `LIVE_RUN_RESULTS/public_release/cli_big_rollout.json`
- `LIVE_RUN_RESULTS/public_release/api_server_log.json`

Final summary:

- API bug-fix: success
- API multi-agent refactor: success
- CLI bug-fix: success
- CLI refactor: success
- CLI migration: success
- CLI repo overview: success
- CLI matrix bug-fix: success
- CLI change runbook: success
- CLI big rollout: success
- generic CLI success count: `7/7`

## Big realistic task result

Big-task artifact:

- `LIVE_RUN_RESULTS/public_release/cli_big_rollout.json`

Prompt:

- `Roll out the new account normalization naming across this monorepo, preserve behavior, update the docs that still mention the old helper, and run the relevant tests.`

Outcome:

- changed files:
  - `apps/api/service.py`
  - `apps/cli/commands.py`
  - `docs/auth.md`
  - `packages/shared/auth.py`
- external validator:
  - `python -m pytest --rootdir . tests/test_service.py tests/test_cli.py -q` -> green
- result: success

## Benchmark results

Curated artifacts:

- `BENCHMARK_RESULTS/final_public_release_live_report.json`
- `BENCHMARK_RESULTS/final_public_release_live_comparison.json`
- `BENCHMARK_RESULTS/final_public_release_offline_report.json`
- `BENCHMARK_RESULTS/final_public_release_live_board/`

Live public benchmark:

- agent: `VIKI Code Live Final 4.1.4`
- total cases: `8`
- passed: `8`
- task completion rate: `1.0`
- pass@1: `1.0`
- median time to green: `90.941s`
- mean case score: `0.975`

Offline public benchmark:

- agent: `VIKI Code Offline Final 4.1.4`
- total cases: `8`
- passed: `8`
- task completion rate: `1.0`
- pass@1: `1.0`
- median time to green: `2.503s`
- mean case score: `1.0`

Head-to-head baseline comparison from the live run:

- completion-rate delta vs Codex: `+0.5`
- completion-rate delta vs Claude Code: `+0.5`
- completion-rate delta vs OpenCode: `+0.5`
- time-to-green is still much worse than all three baselines

## Before / after improvements from this pass

- Before this pass, the broader live suite still had a generic migration miss, the runbook task was nondeterministic, and WSL isolation failed to complete a real live task.
- After this pass, the broader live suite passed `9/9`, the public live benchmark passed `8/8`, the human-style install run passed, and WSL isolation completed a real live bug-fix end to end.

## Remaining limitations and blockers

- VIKI is now a credible public release, but latency remains the biggest weakness.
- The public benchmark breadth is materially better than before, but it is still a repo-specific harness rather than a broad external industry benchmark.
- Docker and Podman were unavailable on this host, so real container validation was blocked and WSL was used as the strongest feasible isolation path.
- Telegram and WhatsApp flows remain harness-tested rather than live-network validated here.

## Secret handling confirmation

- The temporary provider key was used only through process-scoped environment variables.
- The key was not written to source files, docs, benchmark outputs, live artifacts, screenshots, or packaged outputs.
- The raw-key repository scan returned no matches.
- Command and server outputs remained redacted.

## Public-facing release cleanup validation

This final pass stayed focused on branding, packaging, public docs, and GitHub readiness. It did not introduce new live benchmark claims beyond the validated 4.1.4 evidence above.

Additional commands run in this pass:

```bash
gh auth status
python -m pytest
python scripts/install.py --path . --dry-run
python -m build
python -m build
```

Additional results:

- GitHub CLI auth was available for account `rebootix-research`
- README asset references and linked public docs resolved locally
- `python -m pytest` remained green at `59 passed`
- `python scripts/install.py --path . --dry-run` remained successful
- `python -m build` remained successful after the MIT license and manifest cleanup
- stale public-facing clutter was removed from the root and older proof artifact trees were pruned from the public release surface
