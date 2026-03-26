# Smart Memory Gateway — 智能记忆网关

> 面向多 Agent AI 助手的 Scope 感知记忆架构，基于 Mem0 + Qdrant + MCP。

为 AI Agent 提供生产级的持久化结构化记忆，支持群聊隔离、来源追踪、神经科学启发的维护机制和可配置的访问控制。

### 设计目标

1. **最大化模型自主能力** — Agent 自行决定记什么、何时回忆，无需人类干预
2. **减少 Token** — 双路合并、trust 排序、去重、巩固、衰减，把上下文压到最精简
3. **真正维持长久记忆** — 用户画像永不衰减；操作日志在过期前巩固为永久 knowledge

## 核心特性

- **Scope 隔离** — 记忆按 `global`/`group`/`dm`/`agent` 命名空间隔离，群 A 的数据不会泄漏到群 B
- **双查询搜索** — 每次搜索自动合并全局上下文和当前 scope 的结果
- **结构化来源追踪** — 每条记忆附带 `source`、`trust`、`scope`、`mem_type`、`agent` 元数据
- **认知引擎** — 衰减（Bjork 间隔效应）、巩固、冲突检测、级联分类器
- **定时维护** — 每日 Opus 重提取 + 去重；每周巩固 + 冲突解决 + 衰减。通过 CLI + cron 调度（见[维护](#维护调度)）
- **凭证安全** — 正则检测阻止密码、API key、token 被存入记忆
- **优雅降级** — Embedding 主备切换 + 写入队列在 Mem0 不可用时自动排队重放
- **配置驱动** — 所有权限、衰减参数、维护策略集中在一个 `config.yaml`
- **MCP 标准** — 作为 FastMCP Server 运行，兼容任何支持 MCP 的 AI 框架

## 快速开始

### 前置条件

- Python 3.11+
- Qdrant Server（[下载](https://github.com/qdrant/qdrant/releases)）
- Google API Key（用于 `gemini-embedding-001`）或 OpenAI 兼容的 embedding 服务

### 安装

```bash
pip install mem0ai qdrant-client mcp pyyaml pydantic
```

### 配置

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml：设置 API 密钥、Qdrant 地址、Agent 权限
```

### 运行

```bash
# 启动 Qdrant Server
./qdrant --config-path qdrant-config.yaml &

# 启动 MCP Server
python src/server.py
```

### 使用（从 AI Agent 调用）

```python
# 搜索记忆
mcp(action="call", server="mem0", tool="mem0_search",
    args={"query": "用户偏好", "scope": "group:oc_xxx", "limit": 5})

# 存储记忆
mcp(action="call", server="mem0", tool="mem0_add",
    args={"content": "用户喜欢简约风格", "scope": "global",
          "mem_type": "preference", "source": "user_direct", "trust": "high"})

# 健康检查
mcp(action="call", server="mem0", tool="mem0_status", args={})
```

## 架构

```
                 ┌──────────────────────────────┐
                 │     Agent Layer (L1)          │
                 │  Main: 读全域 + 写 global     │
                 │  Workers: 只写 agent:{self}   │
                 └──────────┬───────────────────┘
                            │ MCP (stdio)
                 ┌──────────▼───────────────────┐
                 │  Smart Memory Gateway (L2)    │
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

### 记忆生命周期

| 类型 | 衰减策略 | 用途 |
|------|----------|------|
| `preference` / `fact` | 永不衰减 | 用户画像 — 永久保留 |
| `lesson` / `decision` | 永不衰减 | 经验沉淀 — 永久保留 |
| `knowledge` | 永不衰减 | 从 task_log 巩固而来 |
| `procedure` | 90 天半衰期 | SOP、命令 |
| `task_log` | 30 天半衰期 | 操作日志 → 过期前巩固为 knowledge |

### 维护调度

维护通过独立 CLI 进程运行，由 cron 调度：

```cron
15 2 * * * /path/to/scripts/mem0-backup.sh          # 每日备份
 0 3 * * * /path/to/scripts/run-maintenance.sh daily  # Opus 重提取 + 去重
 0 4 * * 0 /path/to/scripts/run-maintenance.sh weekly # + 冲突检测 + 巩固 + 衰减
```

`mem0_maintenance` MCP 工具提供维护报告和状态查看；实际的维护管线通过 `python src/maintenance.py` 执行。

## 文档

- [架构详解 (v2)](ARCHITECTURE-v2.md) — 完整架构文档，含三个设计目标分析
- [设计文档](docs/design_cn.md) — 完整 9 章系统设计
- [使用指南](docs/usage.md) — 如何集成到你的 AI Agent
- [开发指南](docs/development.md) — 如何扩展和贡献
- [配置参考](docs/configuration.md) — config.yaml 完整选项

## 许可证

MIT — 见 [LICENSE](LICENSE)
