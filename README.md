# copilot_aqualib

AquaLib is a multi-agent Python framework for scientific research tasks, built on the **GitHub Copilot SDK**. It features a two-agent pipeline (Executor + Reviewer), RAG-powered information retrieval, persistent multi-session workspaces, and a generalized **vendor skill ecosystem** with automatic priority enforcement.

## Features

- **Copilot SDK integration**: Built on `github-copilot-sdk` for agent orchestration, tool dispatch, and infinite session management
- **Two-agent pipeline**: Executor (skill dispatch & execution) + Reviewer (quality assurance & audit)
- **Vendor skill priority**: Vendor skills (discovered via `SKILL.md`) are automatically preferred when relevant
- **Multi-session workspaces**: Each project supports multiple named sessions with independent agent memory, history, and vendor traces
- **RAG retrieval**: Optional LlamaIndex-based document and skill description indexing
- **Extensible skill registry**: Mount external skill libraries at runtime via `SKILL.md` contracts
- **Project-aware state**: One directory = one project, with full history recall across sessions

## Installation

### Quick start (with vendor skills included)

```bash
git clone --recursive https://github.com/kzy599/copilot_aqualib.git
cd copilot_aqualib
pip install -e ".[dev]"
```

The `--recursive` flag ensures any vendor submodules (e.g. `vendor/ClawBio`) are cloned along with the main repository, providing real skills out of the box.

### Standard install (without vendor submodules)

```bash
git clone https://github.com/kzy599/copilot_aqualib.git
cd copilot_aqualib
pip install -e ".[dev]"
```

> **Note:** `git clone` and `pip install` only need to be done **once**. After that, the `aqualib` command is available globally in your Python environment. You do NOT need to re-clone or re-install when starting new projects.

## Setup

### 1. Set your API key

AquaLib supports three authentication modes for the Copilot SDK:

**GitHub authentication (default):**

```bash
export GH_TOKEN="ghp-your-github-token"
# or
export GITHUB_TOKEN="ghp-your-github-token"
```

**Bring Your Own Key (BYOK) — use any OpenAI-compatible provider:**

```yaml
# aqualib.yaml
copilot:
  auth: byok
  provider:
    type: openai
    base_url: "https://api.openai.com/v1"
    api_key: "sk-your-key"
  model: gpt-4o
```

**Environment variable shorthand for BYOK:**

```bash
export AQUALIB_PROVIDER_API_KEY="sk-your-key"
export AQUALIB_PROVIDER_BASE_URL="https://api.openai.com/v1"
```

For RAG embeddings, a separate API key can be configured (see **Configuration** below).

### 2. Create a project

```bash
mkdir ~/my_protein_study && cd ~/my_protein_study
aqualib init --name "Protein Study" --description "Investigating protein folding patterns"
```

This creates `aqualib_workspace/` with the following structure:

```
aqualib_workspace/
├── project.json               # Project metadata & cumulative summary
├── context_log.jsonl          # One-line-per-event audit trail (JSONL)
├── work/                      # Intermediate task files (inv_0001/, inv_0002/, ...)
├── results/                   # Final outputs & audit reports
│   └── vendor_traces/         # Vendor skill call logs (JSON per invocation)
├── data/                      # Input data & RAG corpus
├── skills/
│   └── vendor/                # Runtime vendor mount point (per-project)
└── sessions/                  # Multi-session management
    └── <session-slug>/
        ├── session.json       # Session metadata (task count, status, summary)
        ├── memory/            # Agent role-specific memory
        │   ├── executor.json  # Executor agent memory (recent tasks & outputs)
        │   └── reviewer.json  # Reviewer agent memory (verdicts & suggestions)
        ├── results/           # Session-scoped task outputs
        └── vendor_traces/     # Session-scoped vendor skill logs
```

### 3. Add your data

```bash
cp ~/data/proteins.fasta   aqualib_workspace/data/
cp ~/data/drug_targets.csv aqualib_workspace/data/
```

The RAG system automatically indexes all files in `data/` (supports `.txt`, `.md`, `.json`, `.csv`, `.yaml`). The `workspace_search` tool also scans this directory for keyword-based file matching.

### 4. Run tasks

```bash
aqualib run "Align the protein sequences MVKLF and MVKLT"
```

## CLI Reference

AquaLib provides 7 CLI commands. All commands accept `--base-dir` (`-d`) to override the workspace root and `--verbose` (`-v`) for debug logging.

### `aqualib run` — Execute a task

```bash
aqualib run "Your research query here"
```

| Flag | Short | Description |
|------|-------|-------------|
| `--base-dir` | `-d` | Override workspace base directory |
| `--verbose` | `-v` | Enable debug logging |
| `--session` | `-s` | Resume a specific session by slug or prefix |
| `--new-session` | | Force create a new session |
| `--session-name` | | Name for the new session (default: "session") |
| `--skip-rag` | | Skip RAG index build (faster for quick tasks) |

**Examples:**

```bash
# Simple task (auto-creates or resumes active session)
aqualib run "Align the protein sequences MVKLF and MVKLT"

# Skip RAG for faster execution
aqualib run "List all kinase inhibitors" --skip-rag

# Start a new named session
aqualib run "Analyze CYP2D6 variants" --new-session --session-name "cyp2d6-analysis"

# Resume a specific session by prefix
aqualib run "Find more CYP2D6 substrates" --session cyp2d6
```

### `aqualib init` — Initialize a project

```bash
aqualib init --name "Project Name" --description "Project description"
```

Creates `aqualib_workspace/` with all required directories and an initial `project.json`. Running `init` in an existing project is safe — it detects `project.json` and reports the current state.

### `aqualib status` — View project status

```bash
aqualib status
aqualib status --limit 20    # Show up to 20 recent tasks
```

Displays project metadata, task history, active sessions, data files, and skill usage statistics.

### `aqualib sessions` — List sessions

```bash
aqualib sessions
```

Shows all sessions in the current project with their task counts and last activity timestamps.

### `aqualib skills` — List registered skills

```bash
aqualib skills
```

Displays all discovered vendor skills (from all tiers) with names, descriptions, and tags.

### `aqualib tasks` — List completed tasks

```bash
aqualib tasks
```

Shows all completed tasks with IDs, queries, statuses, and skills used.

### `aqualib report` — View audit report

```bash
aqualib report <task-id>
aqualib report <task-id> --format json     # JSON format
aqualib report <task-id> --format markdown  # Markdown format (default)
```

Displays the full audit report for a specific task, including the Reviewer agent's verdict, violations, and suggestions.

## How AquaLib Manages State

### No server, no process, no "close"

AquaLib is a **stateless command-line tool**. Every `aqualib run` is an independent process: start → execute → exit. There is no background daemon, no database, no long-running server. All state is **plain files on disk**:

```
~/project_A/
├── aqualib.yaml                  # Project-specific configuration
└── aqualib_workspace/
    ├── project.json              # Project metadata & summary
    ├── context_log.jsonl         # Full audit trail (JSONL)
    ├── data/                     # Your input data
    ├── results/                  # Task outputs & audit reports
    ├── sessions/                 # Multi-session state & agent memory
    └── work/.rag_index/          # Persisted RAG vector index
```

Because everything is files, there is nothing to "close" or "shut down":

| Scenario | Can you resume? | Why |
|----------|----------------|-----|
| Close the terminal | ✅ | Files are on disk |
| Reboot the server | ✅ | Files are on disk |
| Come back 6 months later | ✅ | Files are on disk |
| Copy directory to another machine | ✅ | Files are on disk |

> **Only caveat:** environment variables (e.g. `GH_TOKEN`) are lost on reboot. Write your API keys in `aqualib.yaml` to avoid re-exporting every session.

### Workspace directory reference

| Path | Purpose |
|------|---------|
| `project.json` | Project ID, name, description, task count, active session, cumulative summary |
| `context_log.jsonl` | JSONL audit trail: user prompts, tool calls, errors, task summaries |
| `work/` | Intermediate files; each vendor skill invocation gets `inv_NNNN/` with `input.json` and `output.json` |
| `data/` | Input data files for RAG indexing and `workspace_search` tool |
| `results/` | Per-task directories (`results/<task_id>/`) with `task_state.json`, `audit_report.json`, `audit_report.md` |
| `results/vendor_traces/` | Global vendor skill execution logs (`{skill}_{timestamp}_{id}.json`) |
| `skills/vendor/` | Per-project vendor skill mount point (highest priority tier) |
| `sessions/` | Multi-session directories (see **Session Management** below) |

### Switching between projects = `cd`

AquaLib resolves **all paths from your current working directory**. There is no "open project" or "close project" command. Simply `cd` into a directory and every `aqualib` command automatically uses that directory's `aqualib.yaml` and `aqualib_workspace/`:

```bash
cd ~/project_A && aqualib run "..."   # → uses ~/project_A/aqualib_workspace/
cd ~/project_B && aqualib run "..."   # → uses ~/project_B/aqualib_workspace/
cd ~/project_A && aqualib status      # → back to Project A, full history intact
```

### Per-project configuration

Each project has its own `aqualib.yaml` in its directory. Different projects can use entirely different LLM providers, models, and RAG settings:

```bash
# Project A: GPT-4o for high-accuracy research
~/project_A/aqualib.yaml → copilot.model: gpt-4o

# Project B: local Ollama for fast iteration
~/project_B/aqualib.yaml → copilot.auth: byok, copilot.provider.base_url: http://localhost:11434/v1
```

### Skill loading scope

Skills are loaded from three tiers. **Tier 2 and 3 are global** (shared across all projects); **Tier 1 is per-project**:

| Tier | Path | Per-project? | Description |
|------|------|-------------|-------------|
| **1 (highest)** | `aqualib_workspace/skills/vendor/` | ✅ Yes | Custom skills specific to this project |
| **2** | `copilot_aqualib/vendor/ClawBio/` | ❌ Global | Vendor submodule, same for all projects |
| **3 (lowest)** | Built-in `src/aqualib/skills/` | ❌ Global | Framework built-in placeholders |

Most users never need per-project skills — all projects share the same skill library. Only customise Tier 1 if a specific project needs a specialised skill.

## Session Management

Sessions allow you to group related tasks within a project. Each session maintains its own agent memory, so the Executor and Reviewer agents remember what they've done in previous tasks within the same session.

### How sessions work

- Every `aqualib run` executes within a session
- If no session flags are provided, AquaLib **resumes the active session** (stored in `project.json["active_session"]`)
- If no active session exists, a new one is created automatically
- Sessions are identified by a **slug**: `{name}-{8-char-uuid}` (e.g., `alignment-a1b2c3d4`)

### Session directory structure

```
sessions/
└── alignment-a1b2c3d4/
    ├── session.json           # Metadata: session_id, task_count, status, summary
    ├── memory/
    │   ├── executor.json      # Executor's memory of recent tasks, skills, and outputs
    │   └── reviewer.json      # Reviewer's memory of verdicts and suggestions
    ├── results/               # Session-scoped results
    └── vendor_traces/         # Session-scoped vendor skill logs
```

### Session lifecycle

```bash
# 1. Start a new named session
aqualib run "Align MVKLF and MVKLT" --new-session --session-name "protein-alignment"
#    → Creates session: protein-alignment-a1b2c3d4
#    → Sets as active session in project.json

# 2. Run more tasks in the same session (auto-resumes active session)
aqualib run "Now align MVKLF and MVKLA"
#    → Resumes protein-alignment-a1b2c3d4
#    → Executor remembers the previous alignment task

# 3. Start a different session for a new line of work
aqualib run "Find CYP2D6 inhibitors" --new-session --session-name "drug-study"
#    → Creates session: drug-study-e5f6a7b8
#    → Now active session switches to drug-study-e5f6a7b8

# 4. Go back to the protein alignment session
aqualib run "Compare alignment scores" --session protein-alignment
#    → Resumes protein-alignment-a1b2c3d4
#    → Agent memory from steps 1–2 is restored

# 5. List all sessions
aqualib sessions
```

### Agent memory per session

Each session stores agent-specific memory (auto-compacted to 20 most recent entries):

- **Executor memory** (`executor.json`): records each task's query, skills used, and output preview
- **Reviewer memory** (`reviewer.json`): records each task's query, verdict, violations, and suggestions

When you resume a session, these memories are injected into the agent system messages, allowing continuity across tasks.

### Session vs. project scope

| Scope | What it tracks | Persisted in |
|-------|---------------|--------------|
| **Project** | All tasks ever run, global summary, project metadata | `project.json`, `context_log.jsonl` |
| **Session** | Tasks within one line of work, agent memory, vendor traces | `sessions/<slug>/` |

A project can have many sessions. The `context_log.jsonl` records all events across all sessions (tagged with `session_slug`), while each session directory contains only that session's agent memory and traces.

## Multi-Project Workflow

AquaLib follows a **one directory = one project** principle. Each project directory is fully self-contained with its own data, results, and history.

### Creating a new project

```bash
mkdir ~/project_A && cd ~/project_A
aqualib init --name "CYP2D6 Drug Interactions" --description "Pharmacogenomics study"
cp ~/datasets/cyp2d6.csv aqualib_workspace/data/
aqualib run "What drugs interact with CYP2D6 poor metabolizers?"
```

### Resuming an existing project

Simply `cd` back into the project directory. All history, data, and results are preserved:

```bash
cd ~/project_A
aqualib status                              # see full project history
aqualib run "Find CYP2D6 inhibitors"       # agents are aware of previous tasks
```

When you run a new task in an existing project, the agents automatically receive:
- **Project name** and accumulated summary
- **Recent task history** (last 5 tasks with queries, results, and skills used)
- **Session-specific agent memory** (if resuming a session)
- **RAG context** from all files in `data/`

This means the agents can build on previous work without you repeating context.

Output when running in a resumed project:

```
📂 Project: CYP2D6 Drug Interactions (3 previous tasks)

🐙 AquaLib Result
  Task:    e5f6a7b8
  Status:  approved ✅
  ...
```

### Checking project status

```bash
cd ~/project_A
aqualib status
```

Output:

```
📂 Project: CYP2D6 Drug Interactions
   Created:  2026-04-01
   Updated:  2026-04-04
   Tasks:    3 (2 approved, 1 needs_revision)
   Data:     1 file in data/ (cyp2d6.csv)
   Skills:   drug_interaction (2×), sequence_alignment (1×)

Recent tasks:
  • [a1b2c3d4] "What drugs interact with CYP2D6?"   ✅ approved
  • [e5f6a7b8] "List all CYP2D6 substrates"          ✅ approved
  • [c9d0e1f2] "Predict metabolizer phenotype"         ⚠️ needs_revision
```

### Running `aqualib init` in an existing project is safe

It detects `project.json` and prints:

```
📂 Existing project found: CYP2D6 Drug Interactions (created 2026-04-01, 3 tasks). Workspace is ready.
```

### Task isolation within a project

Each `aqualib run` creates an isolated task directory. Multiple tasks within one project never conflict:

```bash
aqualib run "Find CYP2D6 inhibitors"       # → results/a1b2c3d4/
aqualib run "Predict drug-drug interactions" # → results/e5f6a7b8/ (separate)
aqualib tasks                                # list all tasks in this project
aqualib report a1b2c3d4                      # view a specific audit report
```

Each skill invocation within a task also gets its own sub-directory (`work/inv_NNNN/`), so different skill calls never overwrite each other's inputs/outputs.

### Quick reference

| Action | Command | Re-clone? | Re-install? | Re-init? |
|--------|---------|-----------|-------------|----------|
| First time setup | `git clone` + `pip install` | — | — | — |
| New project | `mkdir` + `cd` + `aqualib init` | ❌ | ❌ | ✅ |
| New task in same project | `cd ~/project` + `aqualib run "..."` | ❌ | ❌ | ❌ |
| New session in same project | `aqualib run "..." --new-session --session-name "name"` | ❌ | ❌ | ❌ |
| Resume a specific session | `aqualib run "..." --session <slug-prefix>` | ❌ | ❌ | ❌ |
| Switch to another project | `cd ~/other_project` | ❌ | ❌ | ❌ |
| Resume existing project | `cd ~/project` + `aqualib status` or `aqualib run "..."` | ❌ | ❌ | ❌ |
| Update framework | `cd copilot_aqualib && git pull` | ❌ | ❌\* | ❌ |

> \* Re-install only needed if `pyproject.toml` dependencies changed.

## Vendor Skill Ecosystem

AquaLib uses a **three-tier priority** system for vendor skills:

| Priority | Source | Description |
|----------|--------|-------------|
| **1 (highest)** | Runtime mount point | Your custom skills in `aqualib_workspace/skills/vendor/` |
| **2** | Vendor directory | Libraries under `vendor/` (e.g. `vendor/ClawBio`, included via `git clone --recursive`) |
| **3 (lowest)** | Built-in placeholders | Example skills bundled with the framework |

Skills at higher priority levels are never overwritten by lower-priority registrations. This means you can always override a vendor skill with your own version in the runtime mount point.

Every library inside `vendor/` follows the same universal standard:
1. Markdown-driven (`SKILL.md` defines the skill, `AGENTS.md` defines the library rules).
2. Contains a machine-readable index (e.g., `catalog.json`).
3. Executed entirely via subprocess CLI (e.g., `python <file> --output <file> --skill <name>`).

### How vendor skills are executed

When the agent invokes a vendor skill, AquaLib:

1. Creates an isolated invocation directory (`work/inv_NNNN/`)
2. Writes the parameters to `input.json`
3. Runs the vendor CLI via subprocess: `python <entry_point> run <input.json> --output <output.json> --skill <name>`
4. Applies a **300-second timeout** — if the vendor CLI hangs, the process is killed and an error is returned
5. Captures stdout/stderr and saves a trace to `results/vendor_traces/`
6. Returns the content of `output.json` (or stdout) to the agent

Vendor skills with errors are retried up to **4 times** before being skipped.

### Using vendor submodules

If you cloned with `--recursive`, vendor libraries (e.g. `vendor/ClawBio`) are already available and all their skills will be registered automatically when the framework starts.

To update a vendor library:

```bash
git submodule update --remote vendor/ClawBio
```

### Using a custom runtime mount point

Clone or symlink a skill library to the runtime mount point:

```bash
git clone https://github.com/kzy599/ClawBio.git aqualib_workspace/skills/vendor
pip install -r aqualib_workspace/skills/vendor/requirements.txt
```

Skills in this directory take precedence over repo-shipped vendor and built-in skills.

### Writing a custom SKILL.md

Each vendor skill is defined by a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: my_custom_skill
description: Performs custom analysis on input data
version: 1.0.0
tags: analysis, custom
parameters: {"input_file": "string", "threshold": "float"}
---

# My Custom Skill

Detailed documentation for the skill goes here.
Include usage examples, parameter descriptions, and expected output format.
```

The frontmatter is parsed with `yaml.safe_load()`, and tags are expected as a comma-separated string.

### SDK tools available to agents

When a session starts, AquaLib automatically registers these tools:

| Tool | Description |
|------|-------------|
| `vendor_<name>` | One tool per discovered vendor skill |
| `workspace_search` | Keyword search across data files in `data/` |
| `read_skill_doc` | Read full `SKILL.md` documentation (progressive disclosure) |
| `rag_search` | Semantic vector search over data files (if RAG is enabled) |

## Configuration

Create `aqualib.yaml` (generated by `aqualib init`) or set environment variables:

```yaml
copilot:
  auth: github               # "github" (default), "token", or "byok"
  # github_token: ""         # defaults to GH_TOKEN / GITHUB_TOKEN env var
  # provider:                # only needed for "byok" auth
  #   type: openai           # "openai", "azure", or "anthropic"
  #   base_url: ""           # e.g., "https://api.openai.com/v1"
  #   api_key: ""            # reads AQUALIB_PROVIDER_API_KEY env var
  model: gpt-4o
  # reasoning_effort: medium # "low", "medium", "high", or "xhigh"

llm:
  api_key: ""              # defaults to OPENAI_API_KEY env var
  base_url: null           # set for Azure, DeepSeek, Ollama, etc. Also reads AQUALIB_LLM_BASE_URL / OPENAI_BASE_URL
  model: gpt-4o
  temperature: 0.2
  max_tokens: 4096

rag:
  enabled: false           # set to true and install aqualib[rag] to enable
  api_key: ""              # defaults to AQUALIB_RAG_API_KEY env var, then falls back to llm.api_key
  base_url: null           # defaults to AQUALIB_RAG_BASE_URL env var, then falls back to llm.base_url
  chunk_size: 512
  chunk_overlap: 64
  similarity_top_k: 5
  embed_model: text-embedding-3-small

vendor_priority: true      # when true, agents prefer vendor skills over built-in tools

directories:
  base: ./aqualib_workspace
```

### Credential resolution order

| Credential | 1st (highest) | 2nd | 3rd (lowest) |
|---|---|---|---|
| `copilot.github_token` | `aqualib.yaml` | `GH_TOKEN` or `GITHUB_TOKEN` env var | _(empty)_ |
| `copilot.provider.api_key` | `aqualib.yaml` | `AQUALIB_PROVIDER_API_KEY` env var | _(empty)_ |
| `llm.api_key` | `aqualib.yaml` → `llm.api_key` | `OPENAI_API_KEY` env var | _(empty → runtime error)_ |
| `llm.base_url` | `aqualib.yaml` → `llm.base_url` | `AQUALIB_LLM_BASE_URL` or `OPENAI_BASE_URL` env var | `None` (OpenAI default) |
| `rag.api_key` | `aqualib.yaml` → `rag.api_key` | `AQUALIB_RAG_API_KEY` env var | falls back to resolved `llm.api_key` |
| `rag.base_url` | `aqualib.yaml` → `rag.base_url` | `AQUALIB_RAG_BASE_URL` env var | falls back to resolved `llm.base_url` |

### Example: BYOK with OpenAI

```yaml
copilot:
  auth: byok
  provider:
    type: openai
    base_url: "https://api.openai.com/v1"
    api_key: "sk-your-key"
  model: gpt-4o
```

### Example: separate LLM and embedding providers

```bash
# LLM on Azure OpenAI
export AQUALIB_LLM_BASE_URL="https://my-instance.openai.azure.com/"
export OPENAI_API_KEY="azure-api-key"

# Embeddings on official OpenAI
export AQUALIB_RAG_API_KEY="sk-openai-key"
export AQUALIB_RAG_BASE_URL="https://api.openai.com/v1"
```

Or configure the same in `aqualib.yaml`:

```yaml
# Example: Azure OpenAI for LLM, official OpenAI for embeddings
llm:
  api_key: "azure-key-here"
  base_url: "https://my-resource.openai.azure.com/"
  model: gpt-4o

rag:
  api_key: "sk-openai-key-here"
  base_url: null
  embed_model: text-embedding-3-small
```

```yaml
# Example: local Ollama for LLM, OpenAI for embeddings
copilot:
  auth: byok
  provider:
    type: openai
    base_url: "http://localhost:11434/v1"
    api_key: "ollama"
  model: llama3

rag:
  api_key: "sk-openai-key-here"
  base_url: null
  embed_model: text-embedding-3-small
```

## Python API

```python
import asyncio
from aqualib.bootstrap import build_orchestrator
from aqualib.config import Settings, DirectorySettings, LLMSettings, RAGSettings

async def main():
    settings = Settings(
        directories=DirectorySettings(base="./my_workspace").resolve(),
        llm=LLMSettings(model="gpt-4o"),
        rag=RAGSettings(embed_model="text-embedding-3-small"),
        vendor_priority=True,
    )
    orch = await build_orchestrator(settings, skip_rag_index=True)
    task = await orch.run("Align the protein sequences MVKLF and MVKLT")
    print(f"Status: {task.status.value}")

asyncio.run(main())
```

## REST API (Experimental)

> **Note:** The REST API has not been migrated to the Copilot SDK pipeline yet. Running `aqualib-api` will raise `NotImplementedError`. Use the CLI (`aqualib`) as the primary interface.

The REST API is planned for future migration. Once available, install with:

```bash
pip install -e ".[api]"
```

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Lint
ruff check .
```
