# AquaLib v0.2.1 重构 Prompt：Bug 修复 + 多 Session 架构 + 角色记忆 + RAG 自动适配

## 📋 Problem Statement

在 PR #8 (Copilot SDK 迁移) 合并后的 `kzy599/copilot_aqualib` 仓库 `main` 分支上，完成以下三大板块的改造。**请先完整阅读本 prompt 再开始编码。**

---

## 🔴 板块一：Bug 修复 & 残余清理

### 1.1 修复 `aqualib skills` 命令（Critical）

`cli.py` 第 147–164 行的 `skills` 命令引用了已删除的 `bootstrap.py`：

```python
# 当前代码（会崩溃）：
from aqualib.bootstrap import build_registry  # ← bootstrap.py 已被 PR #8 删除
registry = build_registry(settings)
```

**修复方案**：改用 `scanner.scan_all_skill_dirs`，不再依赖旧的 `SkillRegistry`：

```python
@app.command()
def skills(base_dir=..., verbose=...):
    settings = _get_settings(base_dir, verbose)
    from aqualib.workspace.manager import WorkspaceManager
    from aqualib.skills.scanner import scan_all_skill_dirs

    ws = WorkspaceManager(settings)
    skill_metas = scan_all_skill_dirs(settings, ws)

    table = Table(title="Registered Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="magenta")
    table.add_column("Description")
    table.add_column("Tags", style="dim")

    for meta in skill_metas:
        table.add_row(
            f"vendor_{meta.name}",
            str(meta.skill_dir.parent.name),
            meta.description[:80],
            ", ".join(meta.tags),
        )
    console.print(table)
```

### 1.2 修复 `api.py` 引用已删除模块（Critical）

`api.py` 第 25–28 行引用了已删除的 `bootstrap` 和 `orchestrator`：

```python
from aqualib.bootstrap import build_orchestrator, build_registry  # ← 已删除
from aqualib.core.orchestrator import Orchestrator  # ← 已删除
```

**修复方案**：将 API 改为使用 SDK 路径，或暂时标记为不可用并给出清晰错误信息。推荐后者（API 本身就标记为 experimental）：

```python
# api.py 顶部
raise NotImplementedError(
    "The REST API has not been migrated to the Copilot SDK pipeline yet. "
    "Use the CLI: aqualib run '...'"
)
```

或者如果要保留 API 功能，则重写为通过 `AquaLibClient` + `SessionManager` 驱动（参考 `cli.py` 的 `run` 命令实现）。

### 1.3 更新 `aqualib init` 配置模板

`cli.py` 第 246–269 行的 `init` 命令生成的 `aqualib.yaml` 模板只有旧版 `llm/rag` 段，缺少 `copilot:` 段。

**修复方案**：替换配置模板，参考仓库中已有的 `aqualib.yaml.example` 生成完整配置（包含 `copilot:` 段）。直接读取 `aqualib.yaml.example` 作为模板，或在代码中内嵌包含所有段的模板字符串。

### 1.4 清理残余引用

以下旧版引用需要检查并修复（不要删除被其他模块实际使用的文件）：

| 文件 | 问题 | 处置 |
|------|------|------|
| `workspace/manager.py` L444 | `from aqualib.core.message import Task` | **保留** — `load_task()` 反序列化需要 |
| `workspace/manager.py` L465 | `from aqualib.core.message import AuditReport` | **保留** — `load_audit_report()` 需要 |
| `core/message.py` | 被 workspace manager 依赖 | **保留** — 是数据模型定义 |
| `skills/registry.py` | 仅被已删除的 `bootstrap.py` 和 `api.py` 使用 | 修复 api.py 后检查是否还有引用，无引用则可保留（不强制删除） |
| `skills/loader.py` | 被 `scanner.py` L17 `from aqualib.skills.loader import parse_skill_md` 引用 | **保留** — scanner 依赖它的 `parse_skill_md` 函数 |
| `rag/indexer.py` L10 | `from aqualib.skills.registry import SkillRegistry` | 板块二改造时处理 |

---

## 🟡 板块二：RAG 自动适配（可选增强，自动判断）

### 2.1 设计原则

- 如果用户在 `aqualib.yaml` 中配置了 `rag.embed_model` **并且** `llama-index-core` 已安装 → 自动启用 `rag_search` SDK 工具
- 如果未配置或未安装 → 框架正常运行，不报错，不降级，`workspace_search`（关键词 grep）照常可用
- RAG 的检测和注册发生在 `tool_adapter.py` 的 `build_tools_from_skills()` 中

### 2.2 在 `config.py` 中增加 RAG 启用判断

```python
class RAGSettings(BaseModel):
    # ... 现有字段保持不变 ...
    enabled: bool = Field(
        default=False,
        description="Set to true to enable RAG semantic search. Requires pip install aqualib[rag]."
    )
```

环境变量 / yaml 中 `rag.enabled: true` 时启用。**也支持自动检测**：如果 `rag.api_key` 或 `rag.embed_model` 被显式设置了非默认值，且 llama-index 可导入，则自动视为 enabled。

### 2.3 在 `tool_adapter.py` 中增加 `rag_search` 工具

在 `build_tools_from_skills()` 函数末尾，检测 RAG 可用性并注册：

```python
def build_tools_from_skills(settings, workspace):
    # ... 现有 vendor tool + workspace_search + read_skill_doc ...

    # 自动检测并注册 RAG 工具
    rag_tool = _maybe_create_rag_search_tool(settings, workspace)
    if rag_tool is not None:
        tools.append(rag_tool)

    return tools


def _maybe_create_rag_search_tool(settings, workspace):
    """如果 RAG 配置可用且 llama-index 已安装，创建 rag_search SDK 工具。"""
    if not _is_rag_available(settings):
        return None

    try:
        from copilot import define_tool
        from pydantic import BaseModel, Field as PydanticField

        class RAGSearchParams(BaseModel):
            query: str = PydanticField(description="Semantic search query")
            top_k: int = PydanticField(default=5, description="Number of results")

        @define_tool(
            name="rag_search",
            description=(
                "Semantic search over workspace data files using vector embeddings. "
                "More powerful than workspace_search for conceptual queries. "
                "Use when keyword search returns poor results."
            ),
        )
        async def rag_search(params: RAGSearchParams) -> str:
            return await _execute_rag_search(settings, workspace, params.query, params.top_k)

        return rag_search
    except ImportError:
        return None


def _is_rag_available(settings) -> bool:
    """检查 RAG 是否配置且依赖可导入。"""
    try:
        import llama_index.core  # noqa: F401
    except ImportError:
        return False

    rag = settings.rag
    # 显式启用，或 embed_model 被设置且有可用的 API key
    if rag.enabled:
        return True
    if rag.api_key or settings.llm.api_key:
        return True
    return False


async def _execute_rag_search(settings, workspace, query, top_k):
    """执行 RAG 查询，自动处理索引构建/加载。"""
    import json
    from aqualib.rag.indexer import RAGIndexer
    from aqualib.rag.retriever import Retriever

    # RAGIndexer 需要 SkillRegistry，但 SDK 路径不再使用 registry
    # 所以这里创建一个空 registry，只索引 data/ 文件
    from aqualib.skills.registry import SkillRegistry
    empty_registry = SkillRegistry()

    indexer = RAGIndexer(settings, empty_registry)
    await indexer.load_or_build()

    if indexer.index is None:
        return "RAG index is empty — no documents to search."

    retriever = Retriever(indexer.index, top_k=top_k)
    results = await retriever.query_summaries(query)
    return json.dumps(results, indent=2, ensure_ascii=False)
```

### 2.4 修复 `rag/indexer.py` 使其在无 registry 时也能工作

当前 `indexer.py` 的 `build_index()` 依赖 `registry.to_descriptions()` 来索引 skill 描述文档。在 SDK 路径下 registry 可能为空。

**修改**：使 skill 描述索引成为可选——如果 registry 为空就只索引 `data/` 文件：

```python
async def build_index(self) -> None:
    # ... 现有 LlamaIndex 配置代码 ...
    docs = []

    # 1. Skill descriptions（可选，registry 可能为空）
    skill_descs = self.registry.to_descriptions()
    if skill_descs:
        for desc in skill_descs:
            docs.append(Document(text=json.dumps(desc, indent=2), ...))

    # 2. Files in data/（主要数据源）
    # ... 现有代码不变 ...
```

---

## 🔵 板块三：多 Session + 角色记忆架构

### 3.1 目录结构改造

```
aqualib_workspace/
├── project.json                    # 项目级元数据（不再存 session_id）
├── context_log.jsonl               # 全局审计流水（保留，加 session_id 字段）
├── data/                           # 共享数据（只读）
│
├── sessions/                       # ★ 新增：多 session 管理
│   ├── <session-slug>/             # 每个 session 一个目录
│   │   ├── session.json            # session 元数据
│   │   ├── memory/
│   │   │   ├── executor.json       # Executor 角色专属记忆
│   │   │   └── reviewer.json       # Reviewer 角色专属记忆
│   │   ├── results/                # 该 session 的任务输出
│   │   │   └── <task_id>/
│   │   └── vendor_traces/          # 该 session 的 vendor 调用记录
│   │
│   └── <another-session-slug>/
│       └── ...
│
├── work/                           # 临时工作目录（保留）
└── skills/
    └── vendor/                     # Per-project vendor mount（保留）
```

### 3.2 数据模型

#### `session.json`

```json
{
    "session_id": "aqualib-align-conserved-a1b2c3d4",
    "slug": "align-conserved-a1b2c3d4",
    "name": "Sequence Alignment & Conservation",
    "created_at": "2026-04-04T10:00:00Z",
    "updated_at": "2026-04-04T11:30:00Z",
    "task_count": 2,
    "status": "active",
    "summary": "对齐了 MVKLF/MVKLT 序列，发现第 4 位有差异..."
}
```

#### `memory/executor.json`

```json
{
    "agent": "executor",
    "session_slug": "align-conserved-a1b2c3d4",
    "entries": [
        {
            "query": "对齐蛋白质序列 MVKLF 和 MVKLT",
            "skills_used": ["sequence_alignment"],
            "output_preview": "对齐得分 0.85，第 4 位 F→T 替换",
            "timestamp": "2026-04-04T10:05:00Z"
        }
    ]
}
```

#### `memory/reviewer.json`

```json
{
    "agent": "reviewer",
    "session_slug": "align-conserved-a1b2c3d4",
    "entries": [
        {
            "query": "对齐蛋白质序列 MVKLF 和 MVKLT",
            "verdict": "approved",
            "violations": [],
            "suggestions": [],
            "timestamp": "2026-04-04T10:06:00Z"
        }
    ]
}
```

### 3.3 `project.json` 改造

移除 `session_id` 字段（不再绑定单一 session），新增 `active_session` 作为默认恢复目标：

```json
{
    "project_id": "a1b2c3d4",
    "name": "Protein Study",
    "description": "Sequence alignment research",
    "created_at": "2026-04-04T10:00:00Z",
    "updated_at": "2026-04-04T11:30:00Z",
    "task_count": 5,
    "active_session": "align-conserved-a1b2c3d4",
    "tags": [],
    "summary": "5 tasks across 2 sessions..."
}
```

### 3.4 `workspace/manager.py` 改造

新增以下方法（保留所有现有方法的向后兼容性）：

```python
class WorkspaceManager:
    # ====== Session 管理 ======

    def create_session(self, name: str | None = None) -> dict:
        """创建新 session 目录和 session.json，返回元数据。"""
        slug = self._generate_session_slug(name)
        session_dir = self.dirs.base / "sessions" / slug
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "memory").mkdir(exist_ok=True)
        (session_dir / "results").mkdir(exist_ok=True)
        (session_dir / "vendor_traces").mkdir(exist_ok=True)

        meta = {
            "session_id": f"aqualib-{slug}",
            "slug": slug,
            "name": name or slug,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "task_count": 0,
            "status": "active",
            "summary": "",
        }
        (session_dir / "session.json").write_text(json.dumps(meta, indent=2))

        # 设为活跃 session
        self.update_project({"active_session": slug})
        return meta

    def list_sessions(self) -> list[dict]:
        """列出所有 session，按最近更新排序。"""
        sessions_dir = self.dirs.base / "sessions"
        if not sessions_dir.exists():
            return []
        results = []
        for d in sessions_dir.iterdir():
            if d.is_dir() and (d / "session.json").exists():
                results.append(json.loads((d / "session.json").read_text()))
        return sorted(results, key=lambda s: s.get("updated_at", ""), reverse=True)

    def load_session(self, slug: str) -> dict | None:
        """加载指定 session 的元数据。"""
        path = self.dirs.base / "sessions" / slug / "session.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def find_session_by_prefix(self, prefix: str) -> dict | None:
        """根据前缀模糊匹配 session slug。"""
        for s in self.list_sessions():
            if s["slug"].startswith(prefix):
                return s
        return None

    def get_active_session(self) -> dict | None:
        """获取当前活跃 session。"""
        project = self.load_project()
        if not project or not project.get("active_session"):
            return None
        return self.load_session(project["active_session"])

    def session_dir(self, slug: str) -> Path:
        """返回 session 目录路径。"""
        return self.dirs.base / "sessions" / slug

    # ====== 角色记忆 ======

    def load_agent_memory(self, slug: str, agent_name: str) -> dict:
        """加载指定 session 中指定角色的记忆。"""
        path = self.session_dir(slug) / "memory" / f"{agent_name}.json"
        if not path.exists():
            return {"agent": agent_name, "session_slug": slug, "entries": []}
        return json.loads(path.read_text())

    def save_agent_memory(self, slug: str, agent_name: str, memory: dict) -> None:
        """保存角色记忆，自动 compact 到最近 20 条。"""
        entries = memory.get("entries", [])
        if len(entries) > 20:
            memory["entries"] = entries[-20:]
        path = self.session_dir(slug) / "memory" / f"{agent_name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(memory, indent=2, ensure_ascii=False))

    def append_agent_memory_entry(self, slug: str, agent_name: str, entry: dict) -> None:
        """追加一条记忆条目并自动 compact。"""
        memory = self.load_agent_memory(slug, agent_name)
        entry.setdefault("timestamp", now_iso())
        memory["entries"].append(entry)
        self.save_agent_memory(slug, agent_name, memory)

    # ====== Session 级结果和 trace ======

    def session_results_dir(self, slug: str) -> Path:
        d = self.session_dir(slug) / "results"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def session_vendor_traces_dir(self, slug: str) -> Path:
        d = self.session_dir(slug) / "vendor_traces"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def update_session_after_task(self, slug: str, query: str, messages: list) -> None:
        """更新 session.json 计数器和摘要，同时更新全局 project.json。"""
        session_meta = self.load_session(slug)
        if session_meta:
            session_meta["task_count"] = session_meta.get("task_count", 0) + 1
            session_meta["updated_at"] = now_iso()
            # 简单摘要：保留最新 query
            session_meta["summary"] = f"Last: {query[:100]}"
            (self.session_dir(slug) / "session.json").write_text(
                json.dumps(session_meta, indent=2, ensure_ascii=False)
            )

        # 全局 project 也更新
        project = self.load_project()
        if project:
            project["task_count"] = project.get("task_count", 0) + 1
            project["updated_at"] = now_iso()
            project["active_session"] = slug
            project["summary"] = self.build_project_summary()
            self.save_project(project)

        # 全局 context_log 也写一条（带 session_id 标记）
        self.append_context_log({
            "session_slug": slug,
            "task_id": uuid.uuid4().hex[:8],
            "query": query,
            "status": "completed",
            "skills_used": [],
            "timestamp": now_iso(),
        })
```

### 3.5 `sdk/session_manager.py` 改造

改为使用 workspace 的多 session 管理：

```python
class SessionManager:
    def __init__(self, client, settings, workspace, session_slug: str | None = None):
        self.client = client
        self.settings = settings
        self.workspace = workspace
        self._session_slug = session_slug  # None = 使用活跃 session 或创建新的

    async def get_or_create_session(self) -> tuple[Any, str]:
        """返回 (sdk_session, session_slug)。"""
        ws = self.workspace

        if self._session_slug:
            # 显式指定了 session
            session_meta = ws.find_session_by_prefix(self._session_slug)
            if session_meta:
                return await self._try_resume_or_create(session_meta["slug"]), session_meta["slug"]

        # 尝试恢复活跃 session
        active = ws.get_active_session()
        if active:
            try:
                session = await self._resume_session(active["session_id"])
                return session, active["slug"]
            except Exception:
                pass

        # 创建新 session
        new_meta = ws.create_session()
        session = await self._create_session(new_meta["slug"], new_meta["session_id"])
        return session, new_meta["slug"]

    async def _create_session(self, slug: str, session_id: str) -> Any:
        """创建新 SDK session，注入角色记忆到 agent prompts。"""
        from aqualib.sdk.agents import build_custom_agents
        from aqualib.sdk.hooks import build_hooks
        from aqualib.sdk.system_prompt import build_system_message
        from aqualib.skills.tool_adapter import build_tools_from_skills

        session = await self.client.create_session(
            session_id=session_id,
            model=self.settings.copilot.model,
            # ... 其他参数同现有代码 ...
            custom_agents=build_custom_agents(self.settings, self.workspace, slug),
            tools=build_tools_from_skills(self.settings, self.workspace),
            system_message=build_system_message(self.settings, self.workspace),
            hooks=build_hooks(self.settings, self.workspace, slug),
            infinite_sessions={"enabled": True, ...},
        )
        return session
```

### 3.6 `sdk/agents.py` 改造

`build_custom_agents` 接受 `workspace` 和 `session_slug` 参数，注入角色专属记忆：

```python
def build_custom_agents(settings, workspace=None, session_slug=None):
    vendor_priority_str = "ALWAYS" if settings.vendor_priority else "When appropriate,"

    executor_memory_ctx = ""
    reviewer_memory_ctx = ""

    if workspace and session_slug:
        # 加载 Executor 记忆
        exec_mem = workspace.load_agent_memory(session_slug, "executor")
        if exec_mem.get("entries"):
            recent = exec_mem["entries"][-5:]
            executor_memory_ctx = "\n\nYour previous work in this session:\n"
            for e in recent:
                executor_memory_ctx += (
                    f"- Task: \"{e['query']}\" → skills: {', '.join(e.get('skills_used', []))} "
                    f"| result: {e.get('output_preview', 'N/A')[:80]}\n"
                )

        # 加载 Reviewer 记忆
        rev_mem = workspace.load_agent_memory(session_slug, "reviewer")
        if rev_mem.get("entries"):
            recent = rev_mem["entries"][-5:]
            reviewer_memory_ctx = "\n\nYour previous audits in this session:\n"
            for e in recent:
                reviewer_memory_ctx += (
                    f"- Task: \"{e['query']}\" → {e.get('verdict', '?')} "
                    f"| violations: {e.get('violations', [])}\n"
                )

    return [
        {
            "name": "executor",
            "prompt": _EXECUTOR_PROMPT.format(vendor_priority=vendor_priority_str) + executor_memory_ctx,
            "tools": None,
            "infer": True,
        },
        {
            "name": "reviewer",
            "prompt": _REVIEWER_PROMPT + reviewer_memory_ctx,
            "tools": ["grep", "glob", "view", "read_file"],
            "infer": False,
        },
    ]
```

### 3.7 `sdk/hooks.py` 改造

`build_hooks` 接受 `session_slug` 参数，在任务完成后写入角色记忆：

- `on_session_start`：保持现有逻辑（注入项目级上下文）
- `on_post_tool_use`：审计日志写到 session 级的 context_log
- `on_session_end`：追加 Executor 的 compact 记忆条目
- 新增对 Reviewer 结果的记忆写入（在 `cli.py` 的事件循环中处理，当检测到 reviewer 完成时提取 verdict 写入 `reviewer.json`）

```python
def build_hooks(settings, workspace, session_slug=None):
    return {
        "on_session_start": _make_session_start_hook(workspace),
        "on_user_prompt_submitted": _make_prompt_hook(workspace, session_slug),
        "on_pre_tool_use": _make_pre_tool_hook(settings, workspace),
        "on_post_tool_use": _make_post_tool_hook(workspace, session_slug),
        "on_session_end": _make_session_end_hook(workspace, session_slug),
        "on_error_occurred": _make_error_hook(workspace),
    }
```

`on_session_end` 中写入 Executor 记忆：

```python
def _make_session_end_hook(workspace, session_slug):
    async def on_session_end(input_data, invocation):
        if session_slug:
            workspace.append_agent_memory_entry(session_slug, "executor", {
                "query": input_data.get("query", ""),
                "skills_used": input_data.get("skills_used", []),
                "output_preview": str(input_data.get("summary", ""))[:200],
            })
        workspace.finalize_task()
    return on_session_end
```

### 3.8 `cli.py` 改造

#### `run` 命令增加 session 参数

```python
@app.command()
def run(
    query: str = typer.Argument(...),
    base_dir: str | None = typer.Option(None, "--base-dir", "-d"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    session: str | None = typer.Option(None, "--session", "-s",
        help="Resume a specific session (slug or prefix). Default: most recent."),
    new_session: bool = typer.Option(False, "--new-session",
        help="Force create a new session instead of resuming."),
    session_name: str | None = typer.Option(None, "--session-name",
        help="Name for the new session (only with --new-session)."),
    skip_rag: bool = typer.Option(False, "--skip-rag"),
):
    settings = _get_settings(base_dir, verbose)
    from aqualib.workspace.manager import WorkspaceManager
    ws = WorkspaceManager(settings)

    # Session 选择逻辑
    target_slug = None
    if new_session:
        meta = ws.create_session(name=session_name)
        target_slug = meta["slug"]
        rprint(f"[green]🆕 New session: {meta['name']} ({target_slug})[/green]")
    elif session:
        found = ws.find_session_by_prefix(session)
        if found:
            target_slug = found["slug"]
            rprint(f"[cyan]📂 Resuming session: {found['name']} ({target_slug}, {found['task_count']} tasks)[/cyan]")
        else:
            rprint(f"[red]Session '{session}' not found.[/red]")
            raise typer.Exit(1)
    else:
        active = ws.get_active_session()
        if active:
            target_slug = active["slug"]
            rprint(f"[cyan]📂 Session: {active['name']} ({target_slug}, {active['task_count']} tasks)[/cyan]")

    async def _run():
        from aqualib.sdk.client import AquaLibClient
        from aqualib.sdk.session_manager import SessionManager

        async with AquaLibClient(settings) as client:
            sm = SessionManager(client, settings, ws, session_slug=target_slug)
            sdk_session, actual_slug = await sm.get_or_create_session()

            done = asyncio.Event()
            result_messages = []

            def on_event(event):
                # ... 现有事件处理逻辑 ...
                # 增加：检测 reviewer 完成事件，提取 verdict 写入 reviewer 记忆
                if type_val == "subagent.completed":
                    agent_name = getattr(data, "agent_name", "")
                    if agent_name == "reviewer":
                        content = getattr(data, "content", "")
                        ws.append_agent_memory_entry(actual_slug, "reviewer", {
                            "query": query,
                            "verdict": _extract_verdict(content),
                            "violations": _extract_violations(content),
                            "suggestions": _extract_suggestions(content),
                        })

            sdk_session.on(on_event)
            await sdk_session.send(query)
            await done.wait()

            ws.update_session_after_task(actual_slug, query, result_messages)
            return result_messages

    results = asyncio.run(_run())
    # ... 输出面板 ...
```

#### 新增 `sessions` 命令

```python
@app.command()
def sessions(
    base_dir: str | None = typer.Option(None, "--base-dir", "-d"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List all sessions in the current project."""
    settings = _get_settings(base_dir, verbose)
    from aqualib.workspace.manager import WorkspaceManager
    ws = WorkspaceManager(settings)

    all_sessions = ws.list_sessions()
    if not all_sessions:
        rprint("[dim]No sessions found. Run 'aqualib run' to create one.[/dim]")
        return

    active = ws.get_active_session()
    active_slug = active["slug"] if active else ""

    table = Table(title="Sessions")
    table.add_column("", width=2)   # active indicator
    table.add_column("Slug", style="cyan")
    table.add_column("Name")
    table.add_column("Tasks", justify="right")
    table.add_column("Last Updated", style="dim")
    table.add_column("Status")

    for s in all_sessions:
        indicator = "▶" if s["slug"] == active_slug else ""
        table.add_row(
            indicator,
            s["slug"],
            s.get("name", ""),
            str(s.get("task_count", 0)),
            s.get("updated_at", "")[:16],
            s.get("status", "active"),
        )
    console.print(table)
```

### 3.9 向后兼容

- 如果 `sessions/` 目录不存在（旧项目），`aqualib run` 自动创建第一个 session 并迁移 `project.json` 中的 `session_id`（如果有）
- `aqualib tasks` 命令同时检查旧路径 `results/<task_id>/` 和新路径 `sessions/<slug>/results/<task_id>/`
- `aqualib status` 增加显示 session 列表
- 旧的 `update_project_after_task(query, messages)` 方法保留但标记 deprecated，内部转发到 `update_session_after_task`

---

## 📁 受影响文件清单

| 文件 | 变更类型 | 所属板块 |
|------|---------|---------|
| `src/aqualib/cli.py` | 修改 | 板块一 + 板块三 |
| `src/aqualib/api.py` | 修改 | 板块一 |
| `src/aqualib/config.py` | 修改 | 板块二 |
| `src/aqualib/workspace/manager.py` | 修改（大量新增方法） | 板块三 |
| `src/aqualib/sdk/session_manager.py` | 修改 | 板块三 |
| `src/aqualib/sdk/agents.py` | 修改 | 板块三 |
| `src/aqualib/sdk/hooks.py` | 修改 | 板块三 |
| `src/aqualib/skills/tool_adapter.py` | 修改 | 板块二 |
| `src/aqualib/rag/indexer.py` | 修改 | 板块二 |
| `aqualib.yaml.example` | 修改 | 板块二 |
| `tests/test_sessions.py` | 新增 | 板块三 |
| `tests/test_agent_memory.py` | 新增 | 板块三 |
| `tests/test_rag_auto.py` | 新增 | 板块二 |

## 🧪 测试要求

### 板块一测试
- `aqualib skills` 命令正常输出 vendor skill 列表（mock scanner）
- `aqualib init` 生成的 yaml 包含 `copilot:` 段

### 板块二测试
- `_is_rag_available()` 在 llama-index 未安装时返回 False
- `_is_rag_available()` 在 llama-index 已安装且有 api_key 时返回 True
- `build_tools_from_skills()` 在 RAG 可用时返回包含 `rag_search` 的工具列表
- `build_tools_from_skills()` 在 RAG 不可用时正常返回不包含 `rag_search` 的工具列表

### 板块三测试
- `workspace.create_session()` 创建正确的目录结构
- `workspace.list_sessions()` 返回排序正确的列表
- `workspace.find_session_by_prefix()` 模糊匹配正确
- `workspace.load_agent_memory()` / `save_agent_memory()` 正确读写和 compact
- `append_agent_memory_entry()` 自动 compact 到 20 条
- `SessionManager` 在有活跃 session 时恢复，无时创建
- `SessionManager` 在指定 `--session` 时恢复正确的 session
- `build_custom_agents()` 在有角色记忆时正确注入到 prompt
- 向后兼容：旧项目（无 `sessions/` 目录）不崩溃

## ⚠️ 关键约束

1. **所有 LLM 调用必须通过 Copilot SDK**，不得直接使用 `openai.AsyncOpenAI`（RAG 的 embedding 调用除外，那是 LlamaIndex 管的）
2. **角色记忆是纯文件操作**——读 JSON、写 JSON、截断列表，不调用任何 SDK API
3. **RAG 检测必须是静默的**——检测失败不报错、不 warning，只是不注册 `rag_search` 工具
4. **`--session` 参数支持前缀匹配**——用户不需要输入完整 slug
5. **默认行为不变**——不传 `--session` 和 `--new-session` 时，自动恢复最近活跃的 session，首次运行自动创建
