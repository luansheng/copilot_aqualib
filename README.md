# copilot_aqualib

AquaLib is a multi-agent Python framework for scientific research tasks, featuring a three-agent pipeline (Executor, Reviewer, Searcher), RAG-powered information retrieval, and a generalized **vendor skill ecosystem** with automatic priority enforcement.

## Features

- **Three-agent pipeline**: Searcher (RAG-powered context retrieval), Executor (skill dispatch), Reviewer (quality assurance)
- **Vendor skill priority**: Vendor skills are automatically preferred when relevant
- **RAG retrieval**: LlamaIndex-based document and skill description indexing
- **Extensible skill registry**: Mount external skill libraries at runtime
- **Project-aware workspaces**: One directory = one project, with full history recall

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

```bash
export OPENAI_API_KEY="sk-your-openai-key-here"
```

By default a single OpenAI API key drives both the LLM agents and the RAG embedding model. To use separate providers (e.g. Azure for LLM, OpenAI for embeddings), see the **Configuration** section below.

### 2. Create a project

```bash
mkdir ~/my_protein_study && cd ~/my_protein_study
aqualib init --name "Protein Study"
```

This creates `aqualib_workspace/` with the following structure:

```
aqualib_workspace/
├── project.json               # Project metadata & cumulative summary
├── context_log.jsonl          # One-line-per-task history log
├── work/                      # Intermediate task files
├── results/                   # Final outputs & audit reports
│   └── vendor_traces/         # Vendor skill call logs
├── data/                      # Input data & RAG corpus
└── skills/
    └── vendor/                # Runtime vendor mount point
```

### 3. Add your data

```bash
cp ~/data/proteins.fasta   aqualib_workspace/data/
cp ~/data/drug_targets.csv aqualib_workspace/data/
```

The RAG system automatically indexes all files in `data/` (supports `.txt`, `.md`, `.json`, `.csv`, `.yaml`).

### 4. Run tasks

```bash
aqualib run "Align the protein sequences MVKLF and MVKLT"
```

## How AquaLib Manages State

### No server, no process, no "close"

AquaLib is a **stateless command-line tool**. Every `aqualib run` is an independent process: start → execute → exit. There is no background daemon, no database, no long-running server. All state is **plain files on disk**:

```
~/project_A/
├── aqualib.yaml                  # Project-specific configuration
└── aqualib_workspace/
    ├── project.json              # Project metadata & summary
    ├── context_log.jsonl         # Task history log
    ├── data/                     # Your input data
    ├── results/                  # Task outputs & audit reports
    └── work/.rag_index/          # Persisted RAG vector index
```

Because everything is files, there is nothing to "close" or "shut down":

| Scenario | Can you resume? | Why |
|----------|----------------|-----|
| Close the terminal | ✅ | Files are on disk |
| Reboot the server | ✅ | Files are on disk |
| Come back 6 months later | ✅ | Files are on disk |
| Copy directory to another machine | ✅ | Files are on disk |

> **Only caveat:** environment variables (e.g. `OPENAI_API_KEY`) are lost on reboot. Write your API keys in `aqualib.yaml` to avoid re-exporting every session.

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
~/project_A/aqualib.yaml → llm.model: gpt-4o

# Project B: local Ollama for fast iteration
~/project_B/aqualib.yaml → llm.base_url: http://localhost:11434/v1, llm.model: llama3
```

### Skill loading scope

Skills are loaded from three tiers. **Tier 2 and 3 are global** (shared across all projects); **Tier 1 is per-project**:

| Tier | Path | Per-project? | Description |
|------|------|-------------|-------------|
| **1 (highest)** | `aqualib_workspace/skills/vendor/` | ✅ Yes | Custom skills specific to this project |
| **2** | `copilot_aqualib/vendor/ClawBio/` | ❌ Global | Vendor submodule, same for all projects |
| **3 (lowest)** | Built-in `src/aqualib/skills/` | ❌ Global | Framework built-in placeholders |

Most users never need per-project skills — all projects share the same skill library. Only customise Tier 1 if a specific project needs a specialised skill.

## Multi-Project Workflow

AquaLib follows a **one directory = one project** principle. Each project directory is fully self-contained with its own data, results, and history.

### How project switching works

AquaLib resolves the workspace based on your **current working directory** (`cwd`). When you run any `aqualib` command, it looks for `aqualib_workspace/` in `cwd`. No configuration or flags needed — just `cd` into the right directory.

```bash
cd ~/project_A
aqualib run "..."     # uses ~/project_A/aqualib_workspace/

cd ~/project_B
aqualib run "..."     # uses ~/project_B/aqualib_workspace/
```

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

Each skill invocation within a task also gets its own sub-directory (`results/<task_id>/skills/<invocation_id>/`), so different skills never overwrite each other's outputs.

### Quick reference

| Action | Command | Re-clone? | Re-install? | Re-init? |
|--------|---------|-----------|-------------|----------|
| First time setup | `git clone` + `pip install` | — | — | — |
| New project | `mkdir` + `cd` + `aqualib init` | ❌ | ❌ | ✅ |
| New task in same project | `cd ~/project` + `aqualib run "..."` | ❌ | ❌ | ❌ |
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
3. Executed entirely via Subprocess CLI (e.g., `python <file> --output <file> --skill <name>`).

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

## Usage

```bash
# List all registered skills
aqualib skills

# Run a task
aqualib run "Align the protein sequences MVKLF and MVKLT"

# Skip RAG index build (faster for testing)
aqualib run "What drugs interact with CYP2D6 poor metabolizers?" --skip-rag

# Initialise a new project with a custom name and description
aqualib init --name "My Research Project" --description "Protein binding study"

# View completed tasks
aqualib tasks

# View an audit report
aqualib report <task-id>

# Check project status
aqualib status
```

## Configuration

Create `aqualib.yaml` (generated by `aqualib init`) or set environment variables:

```yaml
llm:
  api_key: ""              # defaults to OPENAI_API_KEY env var
  base_url: null           # set for Azure, DeepSeek, Ollama, etc. Also reads AQUALIB_LLM_BASE_URL / OPENAI_BASE_URL
  model: gpt-4o
  temperature: 0.2
  max_tokens: 4096

rag:
  api_key: ""              # defaults to AQUALIB_RAG_API_KEY env var, then falls back to llm.api_key
  base_url: null           # defaults to AQUALIB_RAG_BASE_URL env var, then falls back to llm.base_url
  chunk_size: 512
  chunk_overlap: 64
  similarity_top_k: 5
  embed_model: text-embedding-3-small

vendor_priority: true

directories:
  base: ./aqualib_workspace
```

### Credential resolution order

| Credential | 1st (highest) | 2nd | 3rd (lowest) |
|---|---|---|---|
| `llm.api_key` | `aqualib.yaml` → `llm.api_key` | `OPENAI_API_KEY` env var | _(empty → runtime error)_ |
| `llm.base_url` | `aqualib.yaml` → `llm.base_url` | `AQUALIB_LLM_BASE_URL` or `OPENAI_BASE_URL` env var | `None` (OpenAI default) |
| `rag.api_key` | `aqualib.yaml` → `rag.api_key` | `AQUALIB_RAG_API_KEY` env var | falls back to resolved `llm.api_key` |
| `rag.base_url` | `aqualib.yaml` → `rag.base_url` | `AQUALIB_RAG_BASE_URL` env var | falls back to resolved `llm.base_url` |

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
llm:
  api_key: "ollama"
  base_url: "http://localhost:11434/v1"
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

AquaLib includes an optional REST API built with FastAPI. This is experimental and may change in future versions. The CLI (`aqualib`) remains the primary interface.

### Installation

```bash
pip install -e ".[api]"
```

### Starting the server

```bash
# Via entry point
aqualib-api

# Or directly with uvicorn
uvicorn aqualib.api:app --host 0.0.0.0 --port 8000
```

The server reads `aqualib.yaml` and `aqualib_workspace/` from the **current working directory**, just like the CLI.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/run` | Execute the full agent pipeline |
| `GET` | `/skills` | List all registered skills |
| `GET` | `/tasks` | List completed tasks |
| `GET` | `/tasks/{task_id}` | Get full task state |
| `GET` | `/tasks/{task_id}/report` | Get audit report (JSON or Markdown) |
| `GET` | `/tasks/{task_id}/skills` | List skill invocation outputs |

### Example

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"query": "Align the protein sequences MVKLF and MVKLT"}'
```

> **Note:** This API is experimental. For production use, the CLI is recommended.

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Lint
ruff check .
```
