<div align="center">

# Engram

**Stop maintaining rules.md. Let your AI remember on its own.**

别再手写 rules.md 了——让你的 AI 自己记住。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![Mem0](https://img.shields.io/badge/Mem0-powered-orange.svg)](https://mem0.ai)
[![Qdrant](https://img.shields.io/badge/Qdrant-vector_store-red.svg)](https://qdrant.tech)

*An engram is the trace a memory leaves in the brain. This project does the same for AI — memory that persists across sessions, stays organized, and cleans up after itself.*

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

You've had this experience: you spend 20 minutes explaining your project setup, coding style, or preferences to an AI assistant. It does exactly what you want. Next morning, new session — it knows nothing. You start over.

So you try the workaround: write it all down in a markdown file. `.cursor/rules`, `AGENTS.md`, a system prompt doc — whatever your tool calls it. It works at first. But then:

- The file keeps growing. Every time the AI gets something wrong, you add another rule.
- Old instructions conflict with new ones, and you have to go back and reconcile.
- You realize you're spending more time **maintaining the AI's memory** than doing actual work.
- You have multiple projects, multiple agents — and now multiple files to keep in sync.

You've become a full-time memory manager for your AI. That's backwards.

The deeper problem isn't just "AI forgets." It's that **the burden of remembering falls entirely on you.** You're manually doing what memory should do automatically: deciding what matters, updating when things change, and throwing out what's stale.

Engram flips this. Instead of you maintaining files for the AI, the AI maintains its own memory — structured, scoped, and self-cleaning. It decides what to keep, compresses old information, and forgets what's no longer relevant. You just use it.

```
Today:     You write rules.md → AI reads it → you update rules.md → repeat forever
Engram:    AI remembers on its own → compresses over time → you never maintain a file again
```

## Design Philosophy

### 1. Let the AI manage its own memory

You don't manually save bookmarks for every webpage you visit. Your brain decides what's worth remembering. Engram works the same way — the AI decides what to store, when to recall, and what to ignore. You just use it naturally; memory happens in the background.

### 2. Less is more

Returning 50 old memories into every conversation doesn't help — it wastes tokens and confuses the model. Engram keeps memory lean: duplicates are merged, old logs get summarized into compact knowledge, and stale entries fade away automatically. The result is a small, high-quality set of memories that actually improve responses.

### 3. Important things should last

Not all memories are equal. Your preferences ("always use TypeScript"), lessons learned ("that API has a 5-second timeout"), and key decisions ("we're using PostgreSQL") should never be forgotten. But yesterday's deployment log? That can fade — after being distilled into lasting knowledge first.

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

你一定有过这样的体验：花了 20 分钟跟 AI 助手解释你的项目结构、编码风格、个人偏好。它干得漂亮。第二天，新会话——它什么都不记得了。你只能从头再来。

于是你想了个办法：写个 md 文件。`.cursor/rules`、`AGENTS.md`、系统 prompt 文档——叫什么都行。一开始挺好用。但慢慢地：

- 文件越写越长。每次 AI 搞错什么，你就加一条规则。
- 旧指令和新指令打架，你得回去手动理顺。
- 你发现自己花在**维护 AI 的记忆**上的时间比干正事还多。
- 你有多个项目、多个 Agent——现在还得同步多个文件。

你变成了 AI 的全职记忆管理员。这完全搞反了。

更深层的问题不只是"AI 会忘"，而是**记忆的负担全压在你身上。** 你在手动做记忆系统该自动做的事：判断什么重要、变化时更新、过时了就清掉。

Engram 把这件事翻转过来。不是你替 AI 维护文件，而是 AI 自己维护自己的记忆——结构化的、分域的、能自我清理的。它自己判断什么该留，自动压缩旧信息，自动淡出不再相关的内容。你只管用。

```
现在:     你写 rules.md → AI 读它 → 你更新 rules.md → 无限循环
Engram:   AI 自己记住 → 随时间压缩 → 你再也不用维护文件了
```

## 设计理念

### 1. 让 AI 管理自己的记忆

你不会手动给每个打开过的网页存书签，你的大脑会自己判断什么值得记住。Engram 同理——AI 自己决定存什么、何时回忆、忽略什么。你只管正常使用，记忆在后台自然发生。

### 2. 少即是多

每次对话塞进去 50 条旧记忆并没有帮助——只会浪费 token 和干扰模型。Engram 让记忆保持精简：重复的合并、旧日志浓缩成简洁的知识、过时的条目自动淡出。最终结果是一组小而高质量的记忆，真正能改善回复质量。

### 3. 重要的东西应该持久

不是所有记忆都同等重要。你的偏好（"永远用 TypeScript"）、学到的教训（"那个 API 有 5 秒超时"）、关键决策（"我们用 PostgreSQL"）——这些永远不该被忘记。但昨天的部署日志？它可以慢慢淡出——在被提炼成持久知识之后。

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
