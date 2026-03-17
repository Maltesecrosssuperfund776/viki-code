<div align="center">

<img src="https://github.com/rebootix-research/viki-code/raw/main/assets/logo/viki-code-banner.png" alt="Viki Code" width="600"/>

<br/><br/>

```
The world's first governed coding agent.
No code ships without your approval. Ever.
```

<br/>

[![Release](https://img.shields.io/github/v/release/rebootix-research/viki-code?display_name=tag&style=for-the-badge&color=B08020&labelColor=0E0C0A&label=LATEST)](https://github.com/rebootix-research/viki-code/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10%2B-B08020?style=for-the-badge&labelColor=0E0C0A)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-B08020?style=for-the-badge&labelColor=0E0C0A)](LICENSE)
[![Live Suite](https://img.shields.io/badge/Live%20Suite-9%2F9%20Passing-B08020?style=for-the-badge&labelColor=0E0C0A)](PROOF_REPORT.md)
[![Benchmark](https://img.shields.io/badge/Benchmark-8%2F8%20Passing-B08020?style=for-the-badge&labelColor=0E0C0A)](BENCHMARK_RESULTS)
[![Stars](https://img.shields.io/github/stars/rebootix-research/viki-code?style=for-the-badge&color=B08020&labelColor=0E0C0A)](https://github.com/rebootix-research/viki-code/stargazers)

<br/>

[**Install**](#install)  · 
[**Why Viki Code**](#why-viki-code)  · 
[**How It Works**](#how-it-works)  · 
[**Surfaces**](#surfaces)  · 
[**Proof**](#proof)  · 
[**Docs**](#documentation)

</div>

-----

<br/>

<div align="center">

## Every other coding agent asks you to trust it.

## Viki Code asks you to approve it.

</div>

<br/>

Cursor. GitHub Copilot. Devin. Claude Code. They all operate on the same implicit promise: *trust us.* They generate code, they make changes, they touch your repositories — and they ask you to review after the fact, if at all.

**Viki Code operates on an explicit guarantee: nothing happens without you.**

It is the only autonomous coding system in existence where the governance layer — mandatory human approvals, worktree isolation, instant rollback, live policy validation, and a complete audit trail — is not a setting you toggle on. It is a foundation you cannot turn off.

```
╔═════════════════════════════════════════════════════════════════════════════╗
║                                                                             ║
║   The most powerful coding agent is not the fastest one.                    ║
║   It is the one your team can actually trust with your codebase.            ║
║                                                                             ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

<br/>

-----

## Install

```bash
# One command. Ready in under a minute.
git clone https://github.com/rebootix-research/viki-code.git
cd viki-code
python scripts/install.py --path .
viki
```

That’s it. VIKI opens with a guided setup wizard, detects your provider, and drops you into a prompt-first session. No config files to hunt. No environment variables to memorize. Just type what you want done.

```bash
# Or install from the release wheel
pip install dist/viki_code-4.1.4-py3-none-any.whl

# Or run in Docker
docker pull ghcr.io/rebootix-research/viki-code:latest
docker run --rm -it ghcr.io/rebootix-research/viki-code:latest
```

<br/>

-----

## Why Viki Code

### The problem with every other coding agent

```
┌─────────────────────────────────────────────────────────────────────────┐
│  What happens when you use a normal coding agent:                        │
│                                                                         │
│  You  →  "Fix the auth bug"                                             │
│  AI   →  [Makes 47 changes across 12 files]                             │
│  AI   →  "Done! Here's a summary."                                      │
│  You  →  [Tries to understand what just happened to your codebase]      │
│  You  →  [Finds three new bugs introduced during the "fix"]             │
│  You  →  "How do I undo this?"                                          │
│  AI   →  "..."                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### What happens with Viki Code

```
┌─────────────────────────────────────────────────────────────────────────┐
│  What happens when you use Viki Code:                                   │
│                                                                         │
│  You   →  "Fix the auth bug"                                            │
│  VIKI  →  [Plans the fix, scopes to affected files only]               │
│  VIKI  →  [Shows you a clean diff before touching anything]            │
│  VIKI  →  "Here's what I want to do. Approve?"          ← YOU DECIDE  │
│  You   →  "Yes" / "No" / "Change this part first"                      │
│  VIKI  →  [Executes exactly what was approved]                         │
│  VIKI  →  [Runs tests, validates, confirms green]                      │
│  VIKI  →  [Logs every action with a cryptographic record]              │
│  You   →  [Can undo any of it in one command, any time]                │
└─────────────────────────────────────────────────────────────────────────┘
```

<br/>

The difference is not capability. The difference is **control**.

<br/>

-----

## How It Works

### The Governance Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   1. You state intent                                                           │
│   ─────────────────────────────────────────────────────────────────────────    │
│   viki> Fix the broken calculation in billing.py and make the tests pass       │
│                                                                                 │
│                  │                                                              │
│                  ▼                                                              │
│   2. VIKI plans and scopes                                                      │
│   ─────────────────────────────────────────────────────────────────────────    │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  Planning...                                                         │      │
│   │  ├─ Analyzing repository structure                                  │      │
│   │  ├─ Locating affected symbols: calculate_total(), apply_discount()  │      │
│   │  ├─ Identifying impacted tests: test_billing.py, test_invoices.py  │      │
│   │  └─ Scoping change to 2 files, 3 functions                         │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│                                                                                 │
│                  │                                                              │
│                  ▼                                                              │
│   3. VIKI shows you the diff before touching anything                           │
│   ─────────────────────────────────────────────────────────────────────────    │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  billing.py                                                          │      │
│   │  ─────────────────────────────────────────────────────────────────  │      │
│   │  - total = price * quantity                                          │      │
│   │  + total = round(price * quantity, 2)                               │      │
│   │  - discount = total / discount_rate                                  │      │
│   │  + discount = total * (discount_rate / 100)                         │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│                                                                                 │
│                  │                                                              │
│                  ▼                                                              │
│   4. You approve (or reject, or modify)           ◀── THIS IS MANDATORY       │
│   ─────────────────────────────────────────────────────────────────────────    │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  2 changes staged for billing.py                                    │      │
│   │  Approve this change? [y/n/edit/explain]  _                         │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│                                                                                 │
│                  │                                                              │
│                  ▼                                                              │
│   5. VIKI executes, validates, confirms                                         │
│   ─────────────────────────────────────────────────────────────────────────    │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  Executing approved changes...                                       │      │
│   │  ✓  billing.py patched                                              │      │
│   │  ✓  Running test_billing.py          →  12/12 passed               │      │
│   │  ✓  Running test_invoices.py         →   8/8 passed                │      │
│   │  ✓  Audit record written                                            │      │
│   │  ✓  Rollback path preserved                                         │      │
│   │                                                                      │      │
│   │  Task complete. Undo available with: viki rollback <session_id>     │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

<br/>

### Under the Hood: The Multi-Agent Runtime

VIKI Code runs three specialized agents for every task. Not one model doing everything — three dedicated cognitive roles, each accountable for a distinct part of the pipeline:

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                                                                               │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐  │
│   │                 │    │                 │    │                         │  │
│   │    PLANNER      │───▶│  IMPLEMENTER    │───▶│       VALIDATOR         │  │
│   │                 │    │                 │    │                         │  │
│   │  Understands    │    │  Writes the     │    │  Runs tests. Checks     │  │
│   │  your repo.     │    │  actual code    │    │  policy. Confirms       │  │
│   │  Scopes the     │    │  changes.       │    │  nothing is broken.     │  │
│   │  work. Plans    │    │  Respects the   │    │  Refuses to sign off    │  │
│   │  the safe path. │    │  plan. Stays    │    │  if validation fails.   │  │
│   │                 │    │  in scope.      │    │                         │  │
│   └─────────────────┘    └─────────────────┘    └─────────────────────────┘  │
│                                                                               │
│   Repo intelligence at every stage:                                           │
│   Symbol lookup · Import graph · Impact analysis · Test targeting            │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

<br/>

### Repo Intelligence

VIKI Code does not stuff your entire codebase into a context window and hope. It builds a live model of your repository:

```bash
# See what VIKI knows about your repo
viki repo "auth migration" --path .

# Find symbols across the codebase
viki symbols "normalize_account" --path .

# Understand what changes to a file would affect
viki impact --changed-file viki/api/server.py --path .
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│  viki impact --changed-file src/auth/session.py                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Direct dependents (3):                                                 │
│    src/api/routes/login.py          ← imports session.validate()       │
│    src/middleware/auth.py           ← imports session.refresh()        │
│    tests/test_session.py            ← 14 test cases affected           │
│                                                                         │
│  Indirect dependents (7):                                               │
│    src/api/routes/dashboard.py                                         │
│    src/api/routes/settings.py                                          │
│    ...                                                                  │
│                                                                         │
│  Recommended test scope:                                                │
│    pytest tests/test_session.py tests/test_auth.py                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

<br/>

-----

## What You Can Do

### Real tasks, not toy examples

```bash
# Bug fixes
viki run "Fix the broken calculation in billing.py and make tests pass" --path .

# Refactors
viki run "Refactor auth naming consistently across the codebase and keep all tests green" --path .

# Migrations
viki run "Migrate the old consumer to the new API and run the relevant tests" --path .

# Repo intelligence
viki run "Inspect this repo and give me a full summary of the architecture" --path .

# Multi-step work
viki run "Add input validation to all public API endpoints and write tests for each" --path .
```

### Session management

```bash
# See what's running or completed
viki status . --session-id <session_id>

# Review the diff from any session
viki diff <session_id> --path . --rendered

# Undo everything from a session
viki rollback <session_id> --path .

# Export a patch bundle
viki patch <session_id> --path .
```

<br/>

-----

## Surfaces

### One runtime. Every interface you work in.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐            │
│   │           │   │           │   │           │   │           │            │
│   │   CLI     │   │   API     │   │  VS Code  │   │ Messaging │            │
│   │           │   │           │   │           │   │           │            │
│   └───────────┘   └───────────┘   └───────────┘   └───────────┘            │
│        │               │               │                │                   │
│   Direct terminal  Local HTTP     Repo-aware       Telegram &              │
│   operator use.   REST API for    extension.       WhatsApp.               │
│   Full session    orchestration   Task submission  Approve,                 │
│   control.        and CI/CD.      and approval     reject, diff            │
│                   integration.    from your IDE.   from your phone.        │
│                                                                              │
│                    └─────────────────────────────┘                          │
│                         Same execution core.                                 │
│                         Same governance model.                               │
│                         All surfaces.                                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### CLI

```bash
viki                          # Interactive prompt-first session
viki run "task" --path .      # Direct task execution
viki setup                    # Provider setup wizard
viki setup --repair           # Repair broken setup
viki providers                # List configured providers
viki doctor .                 # Health check your workspace
```

### API

```bash
# Start the local API server
viki up . --host 0.0.0.0 --port 8787
```

```
GET   /healthz                    Health check
GET   /protocol                   API version and capabilities
POST  /runs                       Submit a new task
GET   /runs/{id}                  Task status
GET   /runs/{id}/diff             Diff for a task
GET   /runs/{id}/result           Final result
GET   /approvals                  Pending approvals
POST  /approvals/{id}             Approve or reject
GET   /repo/symbols?q=...         Symbol lookup
GET   /repo/impact?path=...       Impact analysis
```

### VS Code

```bash
viki ide vscode .               # Generate workspace integration
viki ide vscode-extension .     # Full extension setup
```

### Messaging (Telegram & WhatsApp)

```
/status <session_id>     See what's running
/approvals               List pending approvals
/approve <id>            Approve a staged change
/reject <id>             Reject a staged change
/diff <session_id>       See the diff on your phone
/patch <session_id>      Download the patch bundle
/rollback <session_id>   Undo everything
```

<br/>

-----

## Provider Support

VIKI Code works with every major provider. Switch in one command. No code changes.

```
┌────────────────────────────────────────────────────────────────────────┐
│  Supported Providers                                                   │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ✓  Anthropic          (Claude Sonnet, Claude Opus)                   │
│  ✓  OpenAI             (GPT-4o, o1, o3)                               │
│  ✓  NVIDIA NIM         (Kimi K2.5, GLM-5, Llama 3.3)                 │
│  ✓  DashScope / Qwen   (Qwen3-Coder, Qwen3)                          │
│  ✓  OpenRouter         (Any model via unified API)                    │
│  ✓  Azure OpenAI       (Enterprise deployments)                       │
│  ✓  Ollama             (Local models, fully offline)                  │
│  ✓  Generic OpenAI-compatible endpoints                               │
│                                                                        │
│  First-class NVIDIA preset: choose NVIDIA → pick Kimi K2.5 →         │
│  paste key → start prompting. That's it.                              │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

<br/>

-----

## Safety, Approvals, and Rollback

Viki Code is designed to be useful under autonomy without pretending autonomy should be ungoverned.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  GOVERNANCE BY DEFAULT. NOT BY CONFIGURATION.                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────┐   Every task runs in an isolated worktree.           │
│  │  Worktree Isolation  │   The repository is never touched until you         │
│  └──────────────────────┘   approve. Never.                                    │
│                                                                                 │
│  ┌──────────────────────┐   Approval-aware action flow for every              │
│  │  Approval Gate       │   consequential operation. The gate is              │
│  └──────────────────────┘   architectural. Not a setting. Not a flag.         │
│                                                                                 │
│  ┌──────────────────────┐   Diff preview and patch bundle before              │
│  │  Diff Preview        │   anything is applied. See exactly what             │
│  └──────────────────────┘   will change before it changes.                    │
│                                                                                 │
│  ┌──────────────────────┐   One command. Any session. Complete                │
│  │  Instant Rollback    │   reversion. No data loss. No partial              │
│  └──────────────────────┘   states. Clean every time.                         │
│                                                                                 │
│  ┌──────────────────────┐   Every action logged with attribution.             │
│  │  Audit Trail         │   Cryptographic record of everything                │
│  └──────────────────────┘   VIKI touched. Verifiable on demand.              │
│                                                                                 │
│  ┌──────────────────────┐   Sensitive paths, keys, and outputs                │
│  │  Redacted Logs       │   automatically scrubbed from all                   │
│  └──────────────────────┘   proof artifacts and session logs.                 │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

<br/>

-----

## Proof

We publish everything. Every benchmark. Every live run result. Every test. No black box claims.

```
┌────────────────────────────────────────────────────┬──────────┬────────────┐
│  Validation Signal                                 │  Result  │  Version   │
├────────────────────────────────────────────────────┼──────────┼────────────┤
│  Local regression suite                            │  76/76   │  4.1.4     │
│  Live validation suite (fresh repos)               │   9/9    │  4.1.4     │
│  Generic CLI live wins                             │   7/7    │  4.1.4     │
│  Public live benchmark slice                       │   8/8    │  4.1.4     │
│  Public offline benchmark slice                    │   8/8    │  4.1.4     │
│  Human-style install validation                    │  Passed  │  4.1.4     │
│  WSL-isolated live execution                       │  Passed  │  4.1.4     │
└────────────────────────────────────────────────────┴──────────┴────────────┘
```

**Honest limitation:** Viki Code currently trails some baselines on time-to-green even when it completes the task successfully. We document this openly. Speed is a known work item and is being addressed in the active development cycle.

→ **[Full Proof Report](PROOF_REPORT.md)**  ·  **[Benchmark Results](BENCHMARK_RESULTS/)**  ·  **[Live Run Results](LIVE_RUN_RESULTS/)**

<br/>

-----

## Who It Is For

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   Platform & Infrastructure Teams                                               │
│   ──────────────────────────────────────────────────────────────────────────    │
│   You need AI execution that doesn't become a liability. VIKI Code gives       │
│   you automation with approval gates, audit trails, and rollback built in.     │
│                                                                                 │
│   Engineering Teams in Large Repos or Monorepos                                 │
│   ──────────────────────────────────────────────────────────────────────────    │
│   VIKI Code's repo intelligence indexes your structure, understands             │
│   your symbol graph, and scopes work correctly — instead of hallucinating      │
│   changes across files it never read.                                           │
│                                                                                 │
│   Teams That Need Approvals, Rollback, and Proof                                │
│   ──────────────────────────────────────────────────────────────────────────    │
│   Compliance requirements. Security reviews. Regulated industries.             │
│   Viki Code was built for exactly this. Governance is not an add-on.           │
│   It is the entire design philosophy.                                           │
│                                                                                 │
│   Builders Who Want a Serious Local Agent, Not a Hosted Chat UX                 │
│   ──────────────────────────────────────────────────────────────────────────    │
│   Your data stays on your machine. Your code stays in your perimeter.          │
│   Your API key goes to a provider of your choice. Nothing else.                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

<br/>

-----

## vs. The Alternatives

```
                        Cursor     Copilot    Devin    Claude Code   VIKI CODE
                        ──────     ───────    ─────    ───────────   ─────────
  Mandatory approvals     ✗          ✗         ✗           ✗           ✓
  Instant rollback        ✗          ✗         ✗           ✗           ✓
  Cryptographic audit     ✗          ✗         ✗           ✗           ✓
  Worktree isolation      ✗          ✗         ⚠           ✗           ✓
  Diff preview gate       ⚠          ✗         ⚠           ✗           ✓
  Local-first             ✗          ✗         ✗           ✗           ✓
  Multi-agent runtime     ✗          ✗         ✓           ✓           ✓
  Repo intelligence       ✓          ✓         ✓           ✓           ✓
  Messaging surfaces      ✗          ✗         ✗           ✗           ✓
  Provider agnostic       ✗          ✗         ✗           ✗           ✓
  Open source             ✗          ✗         ✗           ✗           ✓
```

<br/>

-----

## The Terminal Experience

VIKI ships with a premium terminal presentation layer. In a capable terminal it renders:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   VIKI Code  v4.1.4                        rebootix-research/viki-code      ║
║   Provider: Anthropic  ·  Model: claude-sonnet-4-20250514                  ║
║   Workspace: /home/user/projects/my-api    Branch: main                     ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   Session: a3f7d291   ·   Started: 14:32:01   ·   Status: Active           ║
║                                                                              ║
║   ┌──────────────────────────────────────────────────────────────────────┐  ║
║   │  ▶  Planner       Scoping fix to billing.py — 2 functions affected  │  ║
║   │  ▶  Implementer   Writing patch...                                   │  ║
║   │  ◷  Validator     Awaiting implementer                               │  ║
║   └──────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

  viki>  _
```

```bash
viki --theme premium run "task" --path .   # Full premium render
viki --theme contrast run "task" --path .  # High contrast
viki --plain run "task" --path .           # Plain output for CI
viki --force-rich --theme premium doctor . # Force themed output
```

<br/>

-----

## Project Structure

```
viki/                  Core runtime, repo intelligence, orchestration,
│                      API, IDE tooling, integrations
│
├── agents/            Planner, Implementer, Validator agents
├── repo/              Repo intelligence — symbols, impact, indexing
├── api/               Local HTTP REST API server
├── ide/               VS Code extension generation
├── integrations/      Telegram, WhatsApp webhook handlers
├── governance/        Approval gate, audit trail, rollback engine
└── ui/                Premium terminal presentation layer

scripts/               Install, validation, live-run, release helpers
tests/                 Unit, integration, CLI, API, regression
BENCHMARK_RESULTS/     Machine-readable benchmark artifacts
LIVE_RUN_RESULTS/      Live validation artifacts
docs/                  Benchmark board and documentation
```

<br/>

-----

## Documentation

|Document            |Description                           |
|--------------------|--------------------------------------|
|<PROOF_REPORT.md>   |Full validation and benchmark evidence|
|<RELEASE_NOTES.md>  |What changed in each release          |
|<AGENTS.md>         |How the multi-agent runtime works     |
|<CONTRIBUTING.md>   |How to contribute to Viki Code        |
|<SECURITY.md>       |Security policy and disclosure        |
|<BENCHMARK_RESULTS/>|All benchmark artifacts               |
|<LIVE_RUN_RESULTS/> |All live run artifacts                |

<br/>

-----

## Contributing

Viki Code is open source and welcomes contributions. Read <CONTRIBUTING.md> before opening a pull request.

If you find a security issue, read <SECURITY.md> and disclose responsibly.

If Viki Code is relevant to your stack — star the repo. It helps more than you think.

<br/>

-----

<div align="center">

```
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║   The most powerful coding agent in the world                         ║
║   is not the fastest one.                                             ║
║                                                                       ║
║   It is the one you can actually trust                                ║
║   with your most important repositories.                              ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
```

<br/>

[![Install](https://img.shields.io/badge/Get%20Started-Install%20Viki%20Code-B08020?style=for-the-badge&labelColor=0E0C0A)](https://github.com/rebootix-research/viki-code#install)
[![Stars](https://img.shields.io/github/stars/rebootix-research/viki-code?style=for-the-badge&color=B08020&labelColor=0E0C0A&label=Star%20on%20GitHub)](https://github.com/rebootix-research/viki-code/stargazers)

<br/>

**Built by [Rebootix Artificial Intelligence Research and Development](https://rebootix-research.com)**

*Sovereign AI Infrastructure · United Arab Emirates · 2026*

</div>