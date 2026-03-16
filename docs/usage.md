# Usage Guide / 使用指南

## Integration with AI Agents / 集成到 AI Agent

### MCP Tool Call Format / MCP 工具调用格式

The MCP server exposes 5 tools. All tool arguments must be passed via the `args` field.

MCP Server 暴露 5 个工具。所有工具参数必须通过 `args` 字段传递。

```python
# Search memories / 搜索记忆
mcp(action="call", server="mem0", tool="mem0_search", args={
    "query": "user preferences",    # Search query / 搜索词
    "scope": "group:my_group",       # Scope filter / 作用域
    "mem_type": "preference",        # Optional type filter / 可选类型过滤
    "trust_min": "medium",           # Optional minimum trust / 可选最低信任度
    "limit": 5                       # Max results / 最大结果数
})

# Add a memory / 存储记忆
mcp(action="call", server="mem0", tool="mem0_add", args={
    "content": "User prefers minimal style",  # Memory content / 记忆内容
    "scope": "global",               # Required! / 必填！
    "mem_type": "preference",        # Memory type / 记忆类型
    "source": "user_direct",         # Source / 来源
    "trust": "high",                 # Trust level / 信任度
    "agent": "main",                 # Writing agent / 写入 agent
    "context": "User said this in chat"  # Context / 上下文
})

# Health check / 健康检查
mcp(action="call", server="mem0", tool="mem0_status", args={})

# Get all memories / 获取全部记忆
mcp(action="call", server="mem0", tool="mem0_get_all", args={
    "scope": "global"                # Optional scope filter / 可选 scope 过滤
})

# Run maintenance / 运行维护
mcp(action="call", server="mem0", tool="mem0_maintenance", args={
    "mode": "daily"                  # daily / weekly / report_only
})
```

## Scope Model / 作用域模型

| Scope | Purpose / 用途 | Searchable from / 可搜索范围 |
|-------|---------|------------------------|
| `global` | Shared across all contexts / 全局共享 | Everywhere / 所有地方 |
| `group:ID` | Group-chat specific / 群聊专属 | That group + global / 该群 + 全局 |
| `dm` | Direct message only / 仅私聊 | DM context / 私聊上下文 |
| `agent:NAME` | Worker-private SOP / Worker 私有 SOP | primary agent / primary agent |
| `all` | Search-only: no filter / 搜索专用：无过滤 | Main DM only / 仅 Main 私聊 |
| `cross:ID` | Search-only: reference another group / 搜索专用：引用其他群 | Main only / 仅 Main |

## Memory Types / 记忆类型

| Type | Lifecycle / 生命周期 | Conflict / 冲突处理 |
|------|---------------------|-------------------|
| `preference` | Permanent (updatable) / 永久(可更新) | Keep latest / 保留最新 |
| `fact` | Permanent (updatable) / 永久(可更新) | Verify source / 验证来源 |
| `procedure` | Half-life 90d / 半衰期 90 天 | Keep latest version / 保留最新版 |
| `lesson` | Permanent / 永久 | No override / 不覆盖 |
| `decision` | Permanent / 永久 | No override / 不覆盖 |
| `task_log` | Half-life 30d / 半衰期 30 天 | No dedup / 不去重 |
| `knowledge` | Permanent / 永久 | Merge latest / 合并最新 |

## Never-Store Rules / 禁止存储规则

The following content is automatically rejected / 以下内容自动拒绝存储：

- API keys (`sk-...`)
- Passwords (`password=...`)
- Tokens (`token=...`)
- Cookies (`cookie=...`)
- PEM private keys

Store summaries instead, e.g., "API key updated on 2026-03-14".
请存储摘要，如"API key 于 2026-03-14 更新"。

## Maintenance / 维护

### Automatic (cron) / 自动（定时任务）

```bash
# Daily at 03:00: Opus re-extract + dedup
0 3 * * * bash scripts/run-maintenance.sh daily

# Weekly Sunday 03:00: daily + consolidation + conflict + decay
0 3 * * 0 bash scripts/run-maintenance.sh weekly

# Daily at 02:30: Qdrant snapshot backup
30 2 * * * bash scripts/mem0-backup.sh
```

### Manual / 手动

```bash
# Run daily maintenance
python src/maintenance.py --mode daily

# Just see a report, no changes
python src/maintenance.py --mode report_only
```

Or ask your primary agent: "run memory maintenance" / 或跟 primary agent 说"跑一下记忆维护"
