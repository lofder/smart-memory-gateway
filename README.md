<div align="center">

# Engram

**Memory traces for AI agents that persist, compress, and never leak.**

记忆痕迹——为 AI Agent 打造的持久、压缩、零泄漏记忆系统。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![Mem0](https://img.shields.io/badge/Mem0-powered-orange.svg)](https://mem0.ai)
[![Qdrant](https://img.shields.io/badge/Qdrant-vector_store-red.svg)](https://qdrant.tech)

*In neuroscience, an **engram** is the physical trace a memory leaves in the brain.*
*Engram does the same for your AI agents — scope-isolated, trust-ranked, and self-maintaining.*

</div>

---

<p align="center">
  <a href="#english">English</a> &nbsp;|&nbsp; <a href="#中文">中文</a>
</p>

<!-- ============================================================ -->
<!-- ENGLISH                                                       -->
<!-- ============================================================ -->

<details open>
<summary><b id="english">English</b></summary>

## Why Engram?

AI agents forget everything between conversations. You tell an agent your preferences, watch it do great work, come back the next day — gone. The typical fix is "just add a vector database", but that creates a worse problem:

- **No isolation** — Agent A reads Agent B's private notes. Group chat memories leak into DMs.
- **No expiration** — Stale memories from months ago pollute every search.
- **No safety** — API keys and passwords get embedded alongside legitimate memories.
- **No compression** — After a month you have 10,000 task logs burning tokens on every context window.

Engram solves this with a **scope-aware, self-maintaining memory layer** that sits between your agents and a vector store:

```
Without Engram:  Agent → flat vector dump → garbage after 2 weeks
With Engram:     Agent → scoped, ranked, compressed memory → useful after 6 months
```

## Design Philosophy

### 1. Agents drive their own memory

The agent — not a human operator — decides what to remember, when to recall, and how to use memories. Engram provides tools; the agent chooses when to call them. No mandatory "save everything" or "retrieve on every message."

### 2. Token budget is sacred

Every memory returned costs tokens. Engram aggressively compresses: dedup (0.92 cosine threshold), consolidation (50 task_logs → 1 knowledge), Bjork decay (stale memories auto-archive), trust ranking (high-quality first), and hard limits on result count.

### 3. Some memories must live forever

User preferences, learned lessons, and consolidated knowledge never decay. Operational logs fade, but before they do, weekly consolidation distills them into permanent knowledge. The result: a memory that gets *better* over time, not noisier.

## MCP Tools

Engram exposes **5 tools** via the MCP protocol. Any MCP-compatible client (Cursor, Claude Desktop, custom agents) can call them:

### `mem0_add` — Store a memory

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | string | **yes** | The memory text |
| `scope` | string | **yes** | `global`, `group:xxx`, `dm`, `agent:xxx` |
| `mem_type` | string | no | `preference`, `fact`, `procedure`, `lesson`, `decision`, `task_log`, `knowledge` |
| `source` | string | no | `user_direct`, `agent_output`, `tool_result`, `inferred` (default: `agent_output`) |
| `trust` | string | no | `high`, `medium`, `low` (default: `medium`) |
| `context` | string | no | Additional context for retrieval |
| `agent` | string | no | Caller identity for permission check |

**Returns**: `{"results": [...]}` on success, `{"queued": true, "write_id": "..."}` if Mem0 is down (auto-replayed later), `{"error": "..."}` on permission/safety violation.

**Guards**: permission check → never_store regex → scope validation → write (or queue).

### `mem0_search` — Dual-query search

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | **yes** | Natural language search query |
| `scope` | string | no | Target scope (default: `global`). Use `cross:group_id` for cross-scope |
| `mem_type` | string | no | Filter by memory type |
| `trust_min` | string | no | Minimum trust level: `high`, `medium`, `low` |
| `limit` | int | no | Max results (default: 5) |
| `agent` | string | no | Caller identity |

**How dual-query works**: When scope is `group:xxx`, Engram runs two parallel searches (group + global), then interleaves results by relevance. You always get the best of both local and global context in one call.

**Returns**: Array of memory objects with `content`, `metadata` (scope, trust, mem_type, source, agent, access_count), sorted by relevance then trust.

### `mem0_get_all` — Full inventory

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | no | User filter (default: `default`) |
| `scope` | string | no | Scope filter |
| `agent` | string | no | Caller identity |

**Returns**: `{"total": N, "results": [...]}` — all active (non-archived) memories matching the filter.

### `mem0_status` — Health check

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent` | string | no | Caller identity |

**Returns**: Full system health including:
- `mem0_ready` / `qdrant_ready` — backend status
- `total_memories` / `active_memories` / `archived_memories`
- `by_scope` — count per scope
- `by_type` — count per memory type
- `by_trust` — count per trust level
- `write_queue_size` — pending offline writes
- `embedding_model` / `config_version` / `schema_version`

### `mem0_maintenance` — Maintenance report

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mode` | string | no | `report_only` (default: `daily`). `daily`/`weekly` are placeholders — run via CLI |
| `agent` | string | no | Caller identity (needs main/devops permission) |

**Note**: The MCP tool generates reports. Actual maintenance (Opus re-extraction, dedup, consolidation, decay) runs via `python src/maintenance.py` scheduled through cron.

## Architecture

### System layers

```
┌─────────────────────────────────────────────────────────────────┐
│  L1: Agent Layer                                                │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │   Main   │  │  Worker  │  │  Worker  │  │  DevOps  │       │
│  │  Agent   │  │  Agent A │  │  Agent B │  │  Agent   │       │
│  │          │  │          │  │          │  │          │       │
│  │ r: all   │  │ r: —     │  │ r: —     │  │ r: all   │       │
│  │ w: global│  │ w: self  │  │ w: self  │  │ w: all   │       │
│  │   group  │  │          │  │          │  │          │       │
│  │   dm     │  │          │  │          │  │          │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │              │              │              │             │
└───────┼──────────────┼──────────────┼──────────────┼─────────────┘
        │              │              │              │
        └──────────────┴──────┬───────┴──────────────┘
                              │ MCP (stdio)
┌─────────────────────────────┼───────────────────────────────────┐
│  L2: Engram MCP Server      ▼                                   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     5 MCP Tools                          │   │
│  │  mem0_add · mem0_search · mem0_get_all                   │   │
│  │  mem0_status · mem0_maintenance                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│  ┌─────────────┐  ┌─────────┴──────────┐  ┌────────────────┐  │
│  │ Permission  │  │   Write Pipeline   │  │  never_store   │  │
│  │ Enforcer    │  │                    │  │  Regex Guard   │  │
│  │             │  │  infer=False       │  │                │  │
│  │ per-agent   │  │  (embedding only,  │  │  blocks keys,  │  │
│  │ read/write  │  │   no LLM call)     │  │  passwords,    │  │
│  │ scope rules │  │                    │  │  tokens        │  │
│  └─────────────┘  │  on failure:       │  └────────────────┘  │
│                   │  → write_queue     │                       │
│                   │    (auto-replay)   │                       │
│                   └────────┬───────────┘                       │
│                            │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐
│   Mem0 SDK   │    │   Qdrant     │    │   Maintenance CLI    │
│              │    │   Server     │    │                      │
│  embedding + │    │              │    │  Daily (3 AM):       │
│  vector write│    │  persistent  │    │  · Opus re-extract   │
│              │    │  vector      │    │  · Vector dedup      │
│  primary:    │    │  storage     │    │                      │
│   Gemini     │    │              │    │  Weekly (Sun 4 AM):  │
│  fallback:   │    │  payload     │    │  · Conflict detect   │
│   OpenAI API │    │  metadata    │    │  · Consolidation     │
│              │    │  filtering   │    │  · Bjork decay       │
└──────────────┘    └──────────────┘    └──────────────────────┘
```

### Data flow: write

```
Agent calls mem0_add("User prefers dark mode", scope="global", mem_type="preference")
  │
  ├─ Permission check: does this agent have write access to "global"?
  ├─ never_store check: does content match any sensitive pattern?
  ├─ Scope validation: is this a writable scope?
  │
  ▼
  Mem0.add(content, metadata={scope, trust, mem_type, source, agent, ...}, infer=False)
  │
  ├─ Success → return result
  └─ Failure → append to write_queue.jsonl → auto-replay on next successful call
```

### Data flow: search

```
Agent calls mem0_search("user preferences", scope="group:team_alpha")
  │
  ├─ Permission check: can this agent read "group:team_alpha"?
  │
  ▼
  Two parallel searches:
  ├─ Search 1: scope="group:team_alpha", archived=false
  └─ Search 2: scope="global", archived=false
  │
  ▼
  Interleave by relevance → trust_min filter → limit → bump access_count (async)
  │
  ▼
  Return: [{content, metadata: {scope, trust, mem_type, ...}}, ...]
```

### Memory lifecycle

| Type | Decay | Lifespan | Purpose |
|------|-------|----------|---------|
| `preference` | **Never** | Permanent | "User prefers dark mode" |
| `fact` | **Never** | Permanent | "Project uses PostgreSQL 16" |
| `lesson` | **Never** | Permanent | "Don't use recursive CTE for this table" |
| `decision` | **Never** | Permanent | "We chose React over Vue for the dashboard" |
| `knowledge` | **Never** | Permanent | Consolidated from task_logs |
| `procedure` | 90-day half-life | Months | "Deploy command: `kubectl apply -f ...`" |
| `task_log` | 30-day half-life | Weeks | "Deployed v2.3 to staging" → consolidates before decay |

### Maintenance pipeline

```
                    ┌─────────┐
                    │  Cron   │
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              ▼                     ▼
     ┌────────────────┐    ┌────────────────┐
     │  Daily (3 AM)  │    │ Weekly (Sun 4) │
     │                │    │                │
     │ 1. Opus re-    │    │ 1. Everything  │
     │    extract     │    │    from daily  │
     │    today's     │    │                │
     │    memories    │    │ 2. Conflict    │
     │                │    │    detection   │
     │ 2. Vector      │    │    (same-scope │
     │    dedup       │    │     fact vs    │
     │    (≥0.92      │    │     fact)      │
     │     cosine)    │    │                │
     │                │    │ 3. Consolidate │
     │ 3. Report      │    │    (N task_log │
     │                │    │     → 1        │
     └────────────────┘    │     knowledge) │
                           │                │
                           │ 4. Bjork decay │
                           │    importance  │
                           │    < 0.10 →    │
                           │    archive     │
                           │                │
                           │ 5. Report      │
                           └────────────────┘
```

**Bjork decay formula**:
```
effective_age = age_days / (1 + min(ln(1 + access_count), 3.0))
importance    = e^(-ln(2)/half_life × effective_age)
```
Frequently accessed memories decay slower. When `importance < 0.10`, the memory is archived.

## Installation

### Step 1: Clone

```bash
git clone https://github.com/lofder/Engram.git
cd Engram
```

### Step 2: Run setup

```bash
./setup.sh
```

This creates `config.yaml` and `.env` from templates. You'll be asked to choose Docker or Local mode.

### Step 3: Set your API key

Edit `.env`:
```bash
GOOGLE_API_KEY=your-google-api-key-here
```

This key is used for `gemini-embedding-001` embeddings. Get one at [Google AI Studio](https://aistudio.google.com/apikey).

### Step 4: Start

**Docker mode** (Qdrant included):
```bash
docker compose up -d
```

**Local mode** (manage Qdrant yourself):
```bash
docker run -d -p 6333:6333 qdrant/qdrant    # or install Qdrant binary
python src/server.py
```

### Step 5: Verify

```bash
# Docker mode
docker compose logs engram | tail -5
# Should show: "engram: initialized OK"

# Local mode — server.py outputs to stderr:
# "engram: initialized OK"
```

### Step 6: Connect your MCP client

**Cursor** — add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "engram": {
      "command": "python",
      "args": ["/absolute/path/to/Engram/src/server.py"],
      "env": {
        "GOOGLE_API_KEY": "your-key",
        "NO_PROXY": "localhost,127.0.0.1"
      }
    }
  }
}
```

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "engram": {
      "command": "python",
      "args": ["/absolute/path/to/Engram/src/server.py"],
      "env": {
        "GOOGLE_API_KEY": "your-key"
      }
    }
  }
}
```

### Step 7: Set up maintenance (optional)

```bash
crontab -e
```
```cron
15 2 * * * /path/to/Engram/scripts/mem0-backup.sh
 0 3 * * * /path/to/Engram/scripts/run-maintenance.sh daily
 0 4 * * 0 /path/to/Engram/scripts/run-maintenance.sh weekly
```

## Real-World Usage

### Scenario 1: Personal preferences across sessions

Your agent learns your style once, remembers it forever:

```
You:    "I prefer concise responses, no bullet points, always include code examples"
Agent:  (calls mem0_add with scope="global", mem_type="preference", trust="high")

--- next day, new session ---

Agent:  (calls mem0_search("response style preferences", scope="global"))
        → gets back: "User prefers concise responses, no bullet points, always include code examples"
        → applies this to all future responses automatically
```

### Scenario 2: Multi-agent team with isolation

A main agent coordinates workers, each with their own memory namespace:

```
Main Agent:     writes to global, group:team, dm
  ├── Writer:   writes to agent:writer only (procedures, task_logs)
  ├── Analyst:  writes to agent:analyst only
  └── Browser:  writes to agent:browser only

Main can search all scopes. Workers can only see their own memories.
No cross-contamination.
```

### Scenario 3: Cross-group context

Your agent needs info from another group without switching context:

```
Agent:  (calls mem0_search("shipping API docs", scope="cross:team_backend"))
        → searches team_backend's memories + global context
        → returns relevant results from both, interleaved by relevance
```

### Scenario 4: Graceful degradation

When Mem0 or the embedding API goes down:

```
Agent:  (calls mem0_add(...))
        → Mem0 unreachable
        → Engram queues the write to write_queue.jsonl
        → Returns: {"queued": true, "write_id": "abc-123", "reason": "Mem0 unavailable"}
        → On next successful mem0_add, queued writes are auto-replayed
```

## Configuration

Key sections in `config.yaml`:

```yaml
# Agent permissions — who can read/write where
agents:
  main:
    read: [global, "group:*", dm, "agent:*", all, "cross:*"]
    write: [global, "group:*", dm]
  worker:
    read: []
    write: ["agent:worker"]
    allowed_types: [procedure, task_log]

# Memory types — each has its own decay and conflict strategy
memory_types:
  preference: {decay: never, conflict: update_latest}
  fact:       {decay: never, conflict: verify_source}
  task_log:   {decay: half_life_30d, conflict: no_dedup}

# Embedding — primary + fallback
embedding:
  primary:
    provider: gemini
    model: models/gemini-embedding-001
    dimensions: 3072
  fallback:
    provider: openai
    model: gemini-embedding-001
    base_url: https://your-proxy.example.com/v1

# Qdrant connection
qdrant:
  host: localhost     # or "qdrant" in docker-compose
  port: 6333
  collection: memories

# Credential safety — these patterns are never stored
never_store_patterns:
  - 'sk-[A-Za-z0-9]{20,}'
  - 'password\s*[:=]\s*\S+'
  - '-----BEGIN\s+(RSA\s+)?PRIVATE'
```

See [docs/configuration.md](docs/configuration.md) for the full reference.

## Documentation

- [Architecture v2](ARCHITECTURE-v2.md) — Full architecture with design goals analysis
- [Design Document (中文)](docs/design_cn.md) — 9-chapter system design
- [Usage Guide](docs/usage.md) — Integration guide
- [Development Guide](docs/development.md) — How to extend
- [Configuration Reference](docs/configuration.md) — All config.yaml options

## Academic Foundation

| Paper | Key Insight | Our Application |
|-------|-------------|-----------------|
| Hindsight (2512.12818) | 4-network memory, 91.4% accuracy | 7 memory type classification |
| MAPLE (2602.13258) | HOT/COLD path separation | Daytime `infer=False` + nightly Opus |
| FadeMem (2601.18642) | Importance-based decay, -45% storage | Bjork-enhanced decay formula |
| OWASP ASI06 (2026) | Memory poisoning risk 40%→80% | trust + never_store + scope isolation |
| Bjork (1992) | Storage-retrieval strength theory | access_count suppresses decay |
| TierMem (2602.17913) | Provenance tracking reduces token | Structured metadata per memory |

## License

MIT — See [LICENSE](LICENSE)

## Contributing

Issues and PRs welcome. Please read [docs/development.md](docs/development.md) first.

</details>

<!-- ============================================================ -->
<!-- 中文                                                          -->
<!-- ============================================================ -->

<details open>
<summary><b id="中文">中文</b></summary>

## 为什么需要 Engram？

AI Agent 在对话之间会遗忘一切。你告诉 Agent 你的偏好，看着它做得很好，第二天回来——全忘了。常见的方案是"加个向量数据库"，但这反而带来更糟的问题：

- **无隔离** — Agent A 能读到 Agent B 的私人笔记，群聊记忆泄漏到私聊
- **无过期** — 几个月前的陈旧记忆污染每次搜索
- **无安全** — API key 和密码跟正常记忆一起被 embedding 存入
- **无压缩** — 一个月后你有上万条 task_log，每次上下文窗口都在烧 token

Engram 用一个**scope 感知、自维护的记忆层**解决这些问题：

```
没有 Engram:  Agent → 扁平向量堆 → 两周后变垃圾
有 Engram:    Agent → 分域、排序、压缩的记忆 → 六个月后仍然有用
```

## 设计理念

### 1. Agent 驱动自己的记忆

Agent——而非人类——决定记什么、何时回忆、如何使用记忆。Engram 提供工具，Agent 选择何时调用。没有强制的"全量保存"或"每条消息都检索"。

### 2. Token 预算神圣不可侵犯

每条返回的记忆都消耗 token。Engram 激进压缩：去重（0.92 余弦阈值）、巩固（50 条 task_log → 1 条 knowledge）、Bjork 衰减（陈旧记忆自动归档）、trust 排序（高质量优先）、返回数量硬限制。

### 3. 有些记忆必须永存

用户偏好、学到的教训和巩固后的 knowledge 永不衰减。操作日志会淡出，但在淡出之前，每周巩固会把它们提炼成永久 knowledge。结果：记忆随时间**变得更好**，而不是更嘈杂。

## MCP 工具

Engram 通过 MCP 协议暴露 **5 个工具**。任何 MCP 兼容客户端（Cursor、Claude Desktop、自定义 Agent）都可以调用：

### `mem0_add` — 存储记忆

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | **是** | 记忆内容 |
| `scope` | string | **是** | `global`、`group:xxx`、`dm`、`agent:xxx` |
| `mem_type` | string | 否 | `preference`、`fact`、`procedure`、`lesson`、`decision`、`task_log`、`knowledge` |
| `source` | string | 否 | `user_direct`、`agent_output`、`tool_result`、`inferred`（默认：`agent_output`） |
| `trust` | string | 否 | `high`、`medium`、`low`（默认：`medium`） |
| `context` | string | 否 | 辅助检索的附加上下文 |
| `agent` | string | 否 | 调用者身份，用于权限校验 |

**返回**：成功 `{"results": [...]}`，Mem0 不可用时 `{"queued": true, "write_id": "..."}`（后续自动重放），权限/安全违规 `{"error": "..."}`。

### `mem0_search` — 双路检索

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | **是** | 自然语言搜索 |
| `scope` | string | 否 | 目标 scope（默认：`global`）。用 `cross:group_id` 跨域搜索 |
| `mem_type` | string | 否 | 按记忆类型过滤 |
| `trust_min` | string | 否 | 最低信任等级：`high`、`medium`、`low` |
| `limit` | int | 否 | 最大返回数（默认：5） |
| `agent` | string | 否 | 调用者身份 |

**双路合并**：当 scope 是 `group:xxx` 时，Engram 并行搜索（group + global），按相关性交错合并。一次调用同时获得本地和全局最佳结果。

### `mem0_get_all` — 全量列举

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | 否 | 用户过滤（默认：`default`） |
| `scope` | string | 否 | scope 过滤 |
| `agent` | string | 否 | 调用者身份 |

### `mem0_status` — 健康检查

返回完整系统状态：后端就绪性、记忆总数/活跃数/归档数、按 scope/类型/信任等级的分布、写入队列大小、embedding 模型版本。

### `mem0_maintenance` — 维护报告

MCP 工具提供报告查看。实际维护（Opus 重提取、去重、巩固、衰减）通过 `python src/maintenance.py` 由 cron 调度执行。

## 架构

### 系统分层

```
┌─────────────────────────────────────────────────────────────────┐
│  L1: Agent 层                                                    │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  Main    │  │ Worker A │  │ Worker B │  │  DevOps  │       │
│  │  Agent   │  │          │  │          │  │  Agent   │       │
│  │          │  │          │  │          │  │          │       │
│  │ 读: 全域  │  │ 读: —    │  │ 读: —    │  │ 读: 全域  │       │
│  │ 写: global│  │ 写: self │  │ 写: self │  │ 写: 全域  │       │
│  │   group  │  │          │  │          │  │          │       │
│  │   dm     │  │          │  │          │  │          │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼──────────────┼──────────────┼──────────────┼─────────────┘
        └──────────────┴──────┬───────┴──────────────┘
                              │ MCP (stdio)
┌─────────────────────────────┼───────────────────────────────────┐
│  L2: Engram MCP Server      ▼                                   │
│                                                                 │
│  5 个工具 · 权限守卫 · never_store 正则 · 写入队列降级            │
│                                                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐
  │   Mem0 SDK   │   │   Qdrant     │   │   维护 CLI (cron)    │
  │  infer=False │   │   向量持久化  │   │                      │
  │  主: Gemini  │   │              │   │  每日: Opus + 去重    │
  │  备: OpenAI  │   │              │   │  每周: +冲突+巩固+衰减 │
  └──────────────┘   └──────────────┘   └──────────────────────┘
```

### 记忆生命周期

| 类型 | 衰减 | 寿命 | 举例 |
|------|------|------|------|
| `preference` | **永不** | 永久 | "用户喜欢简约风格" |
| `fact` | **永不** | 永久 | "项目使用 PostgreSQL 16" |
| `lesson` | **永不** | 永久 | "这个表不要用递归 CTE" |
| `decision` | **永不** | 永久 | "Dashboard 选了 React 而非 Vue" |
| `knowledge` | **永不** | 永久 | 从 task_log 巩固而来 |
| `procedure` | 90 天半衰期 | 数月 | "部署命令：`kubectl apply -f ...`" |
| `task_log` | 30 天半衰期 | 数周 | "部署了 v2.3 到 staging" → 过期前巩固 |

### Bjork 衰减公式

```
effective_age = age_days / (1 + min(ln(1 + access_count), 3.0))
importance    = e^(-ln(2)/半衰期 × effective_age)
```
被检索越多的记忆衰减越慢。当 `importance < 0.10` 时自动归档。

## 安装

### 第 1 步：克隆

```bash
git clone https://github.com/lofder/Engram.git
cd Engram
```

### 第 2 步：运行安装脚本

```bash
./setup.sh
```

自动生成 `config.yaml` 和 `.env`，交互选择 Docker 或本地模式。

### 第 3 步：设置 API Key

编辑 `.env`：
```bash
GOOGLE_API_KEY=你的-google-api-key
```

用于 `gemini-embedding-001` 向量化。在 [Google AI Studio](https://aistudio.google.com/apikey) 获取。

### 第 4 步：启动

**Docker 模式**（含 Qdrant）：
```bash
docker compose up -d
```

**本地模式**：
```bash
docker run -d -p 6333:6333 qdrant/qdrant
python src/server.py
```

### 第 5 步：验证

```bash
# 看到 "engram: initialized OK" 即成功
docker compose logs engram | tail -5
```

### 第 6 步：连接 MCP 客户端

**Cursor** — 添加到 `.cursor/mcp.json`：
```json
{
  "mcpServers": {
    "engram": {
      "command": "python",
      "args": ["/absolute/path/to/Engram/src/server.py"],
      "env": {
        "GOOGLE_API_KEY": "your-key",
        "NO_PROXY": "localhost,127.0.0.1"
      }
    }
  }
}
```

### 第 7 步：配置维护（可选）

```cron
15 2 * * * /path/to/Engram/scripts/mem0-backup.sh
 0 3 * * * /path/to/Engram/scripts/run-maintenance.sh daily
 0 4 * * 0 /path/to/Engram/scripts/run-maintenance.sh weekly
```

## 实际使用场景

### 场景 1：跨会话的个人偏好

Agent 学一次，永远记住：

```
你:     "我喜欢简洁的回复，不要列表，一定要带代码示例"
Agent:  (调用 mem0_add, scope="global", mem_type="preference", trust="high")

--- 第二天，新会话 ---

Agent:  (调用 mem0_search("回复风格偏好", scope="global"))
        → 返回: "用户喜欢简洁回复，不要列表，一定要带代码示例"
        → 自动应用到所有后续回复
```

### 场景 2：多 Agent 团队隔离

Main Agent 协调 Worker，各有独立记忆空间：

```
Main Agent:     写 global, group:team, dm
  ├── Writer:   只写 agent:writer（procedure, task_log）
  ├── Analyst:  只写 agent:analyst
  └── Browser:  只写 agent:browser

Main 可搜索所有 scope。Worker 只看到自己的记忆。零交叉污染。
```

### 场景 3：跨群记忆引用

```
Agent:  (调用 mem0_search("物流API文档", scope="cross:team_backend"))
        → 同时搜索 team_backend 的记忆 + global 上下文
        → 按相关性交错返回两边的结果
```

### 场景 4：优雅降级

Mem0 或 embedding API 挂了：

```
Agent:  (调用 mem0_add(...))
        → Mem0 不可达
        → Engram 把写入排入 write_queue.jsonl
        → 返回: {"queued": true, "write_id": "abc-123"}
        → 下次成功写入时自动重放队列
```

## 配置说明

`config.yaml` 核心段落：

```yaml
# Agent 权限 — 谁可以在哪里读写
agents:
  main:
    read: [global, "group:*", dm, "agent:*", all, "cross:*"]
    write: [global, "group:*", dm]
  worker:
    read: []
    write: ["agent:worker"]
    allowed_types: [procedure, task_log]

# 记忆类型 — 各有独立的衰减和冲突策略
memory_types:
  preference: {decay: never, conflict: update_latest}
  fact:       {decay: never, conflict: verify_source}
  task_log:   {decay: half_life_30d, conflict: no_dedup}

# 安全 — 匹配这些正则的内容永远不会被存储
never_store_patterns:
  - 'sk-[A-Za-z0-9]{20,}'
  - 'password\s*[:=]\s*\S+'
```

完整配置参考见 [docs/configuration.md](docs/configuration.md)。

## 文档

- [架构详解 (v2)](ARCHITECTURE-v2.md) — 完整架构，含三个设计目标分析
- [设计文档](docs/design_cn.md) — 9 章系统设计
- [使用指南](docs/usage.md) — 集成指南
- [开发指南](docs/development.md) — 如何扩展
- [配置参考](docs/configuration.md) — config.yaml 完整选项

## 学术基础

| 论文 | 核心洞察 | 本项目的应用 |
|------|----------|-------------|
| Hindsight (2512.12818) | 4 网络记忆，91.4% 准确率 | 7 种记忆类型分类 |
| MAPLE (2602.13258) | HOT/COLD 路径分离 | 白天 `infer=False` + 夜间 Opus |
| FadeMem (2601.18642) | 基于重要性的衰减，-45% 存储 | Bjork 增强衰减公式 |
| OWASP ASI06 (2026) | 记忆投毒风险 40%→80% | trust + never_store + scope 隔离 |
| Bjork (1992) | 存储-检索强度理论 | access_count 抑制衰减 |
| TierMem (2602.17913) | 来源追踪减少 token | 每条记忆的结构化元数据 |

## 许可证

MIT — 见 [LICENSE](LICENSE)

## 贡献

欢迎提 Issue 和 PR。请先阅读 [docs/development.md](docs/development.md)。

</details>
