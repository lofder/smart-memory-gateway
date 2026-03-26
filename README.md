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

A production-grade memory system that gives AI agents persistent, structured memory with group-chat isolation, provenance tracking, neuroscience-inspired maintenance, and configurable access control.

### Design Goals

1. **Maximize agent autonomy** — Agents decide what to remember and when to recall, no human intervention needed
2. **Minimize token usage** — Dual-query merging, trust-based ranking, dedup, consolidation, and decay keep context lean
3. **Truly persistent memory** — User profile memories never decay; operational logs consolidate into permanent knowledge

### Features

- **Scope Isolation** — Memories are scoped to `global`, `group`, `dm`, or `agent` namespaces. Group A's data never leaks to Group B.
- **Dual-Query Search** — Automatically merges global context with current scope results in every search.
- **Structured Provenance** — Every memory carries `source`, `trust`, `scope`, `mem_type`, and `agent` metadata.
- **Cognitive Engines** — Decay (Bjork-inspired), consolidation, conflict detection, and cascade classification.
- **Scheduled Maintenance** — Daily Opus re-extraction + dedup; weekly consolidation + conflict resolution + decay. Runs via CLI + cron (see [Maintenance](#maintenance)).
- **Credential Safety** — Regex-based `never_store` rules block passwords, API keys, and tokens from being memorized.
- **Graceful Degradation** — Embedding primary/fallback switching + write queue replay when Mem0 is unavailable.
- **Config-Driven** — All permissions, decay parameters, and maintenance schedules in one `config.yaml`.
- **MCP Standard** — Runs as a FastMCP server, compatible with any MCP-enabled AI framework.

### Quick Start

**Prerequisites**: Python 3.11+, Qdrant Server ([download](https://github.com/qdrant/qdrant/releases)), Google API Key or OpenAI-compatible embedding provider.

```bash
pip install mem0ai qdrant-client mcp pyyaml pydantic

cp config.example.yaml config.yaml
# Edit config.yaml: set your API keys, Qdrant host, agent permissions

./qdrant --config-path qdrant-config.yaml &
python src/server.py
```

**Use from your AI agent:**

```python
mcp(action="call", server="mem0", tool="mem0_search",
    args={"query": "user preferences", "scope": "group:my_group", "limit": 5})

mcp(action="call", server="mem0", tool="mem0_add",
    args={"content": "User prefers minimal style", "scope": "global",
          "mem_type": "preference", "source": "user_direct", "trust": "high"})

mcp(action="call", server="mem0", tool="mem0_status", args={})
```

### Architecture

```
                 ┌──────────────────────────────┐
                 │     Agent Layer (L1)          │
                 │  Main: read all, write global │
                 │  Workers: write agent:{self}  │
                 └──────────┬───────────────────┘
                            │ MCP (stdio)
                 ┌──────────▼───────────────────┐
                 │       Engram (L2)             │
                 │                               │
                 │  5 MCP Tools:                 │
                 │  • mem0_add     (write)       │
                 │  • mem0_search  (dual-query)  │
                 │  • mem0_get_all (full scan)   │
                 │  • mem0_status  (health)      │
                 │  • mem0_maintenance (report)  │
                 │                               │
                 │  Guards:                      │
                 │  • Per-agent permissions      │
                 │  • never_store regex          │
                 │  • Write queue (degradation)  │
                 └──────────┬───────────────────┘
                            │
           ┌────────────────┼───────────────┐
           ▼                ▼               ▼
  ┌──────────────┐  ┌────────────┐  ┌──────────────┐
  │  Mem0 SDK    │  │  Qdrant    │  │ Maintenance  │
  │  infer=False │  │  Server    │  │ CLI (cron)   │
  │  (fast write)│  │            │  │              │
  └──────────────┘  └────────────┘  │ Daily:       │
                                    │ • Opus re-   │
                                    │   extract    │
                                    │ • Dedup      │
                                    │              │
                                    │ Weekly:      │
                                    │ • Conflict   │
                                    │ • Consolidate│
                                    │ • Decay      │
                                    └──────────────┘
```

#### Memory Lifecycle

| Type | Decay | Purpose |
|------|-------|---------|
| `preference` / `fact` | Never | User profile — persists forever |
| `lesson` / `decision` | Never | Experience — persists forever |
| `knowledge` | Never | Consolidated from task_logs |
| `procedure` | 90-day half-life | SOPs, commands |
| `task_log` | 30-day half-life | Operational logs → consolidated before decay |

#### Maintenance

Maintenance runs as a separate CLI process, scheduled via cron:

```cron
15 2 * * * /path/to/scripts/mem0-backup.sh          # Daily backup
 0 3 * * * /path/to/scripts/run-maintenance.sh daily  # Opus re-extract + dedup
 0 4 * * 0 /path/to/scripts/run-maintenance.sh weekly # + conflict + consolidate + decay
```

The `mem0_maintenance` MCP tool provides maintenance reports and status; the actual maintenance pipeline runs via `python src/maintenance.py`.

### Documentation

- [Architecture v2](ARCHITECTURE-v2.md) — Full architecture document with three design goals analysis
- [Design Document (中文)](docs/design_cn.md) — Full 9-chapter system design
- [Usage Guide](docs/usage.md) — How to integrate with your AI agent
- [Development Guide](docs/development.md) — How to extend and contribute
- [Configuration Reference](docs/configuration.md) — All config.yaml options

### Academic Foundation

| Paper | Key Insight | Our Application |
|-------|-------------|-----------------|
| Hindsight (2512.12818) | 4-network memory, 91.4% accuracy | 7 memory type classification |
| MAPLE (2602.13258) | HOT/COLD path separation | Daytime fast write (`infer=False`) + nightly Opus deep processing |
| FadeMem (2601.18642) | Importance-based decay, -45% storage | Bjork-enhanced decay formula |
| OWASP ASI06 (2026) | Memory poisoning risk 40%→80% | trust + never_store + scope isolation |
| Bjork (1992) | Storage-retrieval strength theory | access_count suppresses decay |
| TierMem (2602.17913) | Provenance tracking reduces token | Structured metadata per memory |

### License

MIT — See [LICENSE](LICENSE)

### Contributing

Issues and PRs welcome. Please read [docs/development.md](docs/development.md) first.

</details>

<!-- ============================================================ -->
<!-- 中文                                                          -->
<!-- ============================================================ -->

<details open>
<summary><b id="中文">中文</b></summary>

为 AI Agent 提供生产级的持久化结构化记忆，支持群聊隔离、来源追踪、神经科学启发的维护机制和可配置的访问控制。

### 设计目标

1. **最大化模型自主能力** — Agent 自行决定记什么、何时回忆，无需人类干预
2. **减少 Token** — 双路合并、trust 排序、去重、巩固、衰减，把上下文压到最精简
3. **真正维持长久记忆** — 用户画像永不衰减；操作日志在过期前巩固为永久 knowledge

### 核心特性

- **Scope 隔离** — 记忆按 `global`/`group`/`dm`/`agent` 命名空间隔离，群 A 的数据不会泄漏到群 B
- **双查询搜索** — 每次搜索自动合并全局上下文和当前 scope 的结果
- **结构化来源追踪** — 每条记忆附带 `source`、`trust`、`scope`、`mem_type`、`agent` 元数据
- **认知引擎** — 衰减（Bjork 间隔效应）、巩固、冲突检测、级联分类器
- **定时维护** — 每日 Opus 重提取 + 去重；每周巩固 + 冲突解决 + 衰减。通过 CLI + cron 调度（见[维护调度](#维护调度)）
- **凭证安全** — 正则检测阻止密码、API key、token 被存入记忆
- **优雅降级** — Embedding 主备切换 + 写入队列在 Mem0 不可用时自动排队重放
- **配置驱动** — 所有权限、衰减参数、维护策略集中在一个 `config.yaml`
- **MCP 标准** — 作为 FastMCP Server 运行，兼容任何支持 MCP 的 AI 框架

### 快速开始

**前置条件**：Python 3.11+、Qdrant Server（[下载](https://github.com/qdrant/qdrant/releases)）、Google API Key 或 OpenAI 兼容 embedding 服务。

```bash
pip install mem0ai qdrant-client mcp pyyaml pydantic

cp config.example.yaml config.yaml
# 编辑 config.yaml：设置 API 密钥、Qdrant 地址、Agent 权限

./qdrant --config-path qdrant-config.yaml &
python src/server.py
```

**从 AI Agent 调用：**

```python
mcp(action="call", server="mem0", tool="mem0_search",
    args={"query": "用户偏好", "scope": "group:oc_xxx", "limit": 5})

mcp(action="call", server="mem0", tool="mem0_add",
    args={"content": "用户喜欢简约风格", "scope": "global",
          "mem_type": "preference", "source": "user_direct", "trust": "high"})

mcp(action="call", server="mem0", tool="mem0_status", args={})
```

### 架构

```
                 ┌──────────────────────────────┐
                 │     Agent Layer (L1)          │
                 │  Main: 读全域 + 写 global     │
                 │  Workers: 只写 agent:{self}   │
                 └──────────┬───────────────────┘
                            │ MCP (stdio)
                 ┌──────────▼───────────────────┐
                 │       Engram (L2)             │
                 │                               │
                 │  5 个 MCP 工具：               │
                 │  • mem0_add     (写入)         │
                 │  • mem0_search  (双路检索)     │
                 │  • mem0_get_all (全量扫描)     │
                 │  • mem0_status  (健康检查)     │
                 │  • mem0_maintenance (报告)     │
                 │                               │
                 │  守卫：                        │
                 │  • Per-agent 权限              │
                 │  • never_store 正则            │
                 │  • Write queue (降级)          │
                 └──────────┬───────────────────┘
                            │
           ┌────────────────┼───────────────┐
           ▼                ▼               ▼
  ┌──────────────┐  ┌────────────┐  ┌──────────────┐
  │  Mem0 SDK    │  │  Qdrant    │  │ 维护 CLI     │
  │  infer=False │  │  Server    │  │ (cron 调度)  │
  │  (快速写入)   │  │            │  │              │
  └──────────────┘  └────────────┘  │ 每日：       │
                                    │ • Opus 重提取│
                                    │ • 向量去重   │
                                    │              │
                                    │ 每周：       │
                                    │ • 冲突检测   │
                                    │ • 记忆巩固   │
                                    │ • Bjork 衰减 │
                                    └──────────────┘
```

#### 记忆生命周期

| 类型 | 衰减策略 | 用途 |
|------|----------|------|
| `preference` / `fact` | 永不衰减 | 用户画像 — 永久保留 |
| `lesson` / `decision` | 永不衰减 | 经验沉淀 — 永久保留 |
| `knowledge` | 永不衰减 | 从 task_log 巩固而来 |
| `procedure` | 90 天半衰期 | SOP、命令 |
| `task_log` | 30 天半衰期 | 操作日志 → 过期前巩固为 knowledge |

#### 维护调度

维护通过独立 CLI 进程运行，由 cron 调度：

```cron
15 2 * * * /path/to/scripts/mem0-backup.sh          # 每日备份
 0 3 * * * /path/to/scripts/run-maintenance.sh daily  # Opus 重提取 + 去重
 0 4 * * 0 /path/to/scripts/run-maintenance.sh weekly # + 冲突检测 + 巩固 + 衰减
```

`mem0_maintenance` MCP 工具提供维护报告和状态查看；实际的维护管线通过 `python src/maintenance.py` 执行。

### 文档

- [架构详解 (v2)](ARCHITECTURE-v2.md) — 完整架构文档，含三个设计目标分析
- [设计文档](docs/design_cn.md) — 完整 9 章系统设计
- [使用指南](docs/usage.md) — 如何集成到你的 AI Agent
- [开发指南](docs/development.md) — 如何扩展和贡献
- [配置参考](docs/configuration.md) — config.yaml 完整选项

### 学术基础

| 论文 | 核心洞察 | 本项目的应用 |
|------|----------|-------------|
| Hindsight (2512.12818) | 4 网络记忆，91.4% 准确率 | 7 种记忆类型分类 |
| MAPLE (2602.13258) | HOT/COLD 路径分离 | 白天快速写入（`infer=False`）+ 夜间 Opus 深度处理 |
| FadeMem (2601.18642) | 基于重要性的衰减，-45% 存储 | Bjork 增强衰减公式 |
| OWASP ASI06 (2026) | 记忆投毒风险 40%→80% | trust + never_store + scope 隔离 |
| Bjork (1992) | 存储-检索强度理论 | access_count 抑制衰减 |
| TierMem (2602.17913) | 来源追踪减少 token | 每条记忆的结构化元数据 |

### 许可证

MIT — 见 [LICENSE](LICENSE)

### 贡献

欢迎提 Issue 和 PR。请先阅读 [docs/development.md](docs/development.md)。

</details>
