# Configuration Reference / 配置参考

All configuration is in `config.yaml`. Copy from `config.example.yaml` to get started.

所有配置集中在 `config.yaml`。从 `config.example.yaml` 复制开始。

## Agent Permissions / Agent 权限

```yaml
agents:
  main:
    read: [global, "group:*", dm, "agent:*", all, "cross:*"]
    write: [global, "group:*", dm]
    allowed_types: [preference, fact, procedure, lesson, decision, task_log, knowledge]
  worker_example:
    read: []                        # Cannot read directly / 不能直接读
    write: ["agent:worker_example"] # Can only write to own domain / 只能写自己域
    allowed_types: [procedure, task_log]

# Fallback for unconfigured agents / 未配置 agent 的默认策略
default_agent_policy:
  read: [global]
  write: []
  allowed_types: []
```

## Memory Types / 记忆类型

```yaml
memory_types:
  preference: { decay: never, conflict: update_latest }
  fact: { decay: never, conflict: verify_source }
  procedure: { decay: half_life_90d, conflict: keep_latest_version }
  lesson: { decay: never, conflict: no_override }
  task_log: { decay: half_life_30d, conflict: no_dedup }
  decision: { decay: never, conflict: no_override }
  knowledge: { decay: never, conflict: merge_latest }
```

## Maintenance / 维护

```yaml
maintenance:
  daily_time: "03:00"
  weekly_day: sunday
  weekly_window_minutes: 30
  dedup_auto_threshold: 0.92       # Auto-merge above this / 自动合并阈值
  dedup_candidate_threshold: 0.85  # LLM review range / LLM 判断范围
  llm_chain:                       # Fallback chain / 降级链
    - your-provider/claude-opus-4-6
    - your-provider-2/claude-opus-4-6
    - your-provider-4/gpt-5.4
```

## Decay Parameters / 衰减参数

```yaml
decay:
  task_log_half_life_days: 30
  procedure_half_life_days: 90
  access_count_cap: 3.0            # max log factor / log 因子上限
  archive_threshold: 0.10          # Below this → archived / 低于此值归档
```

## Embedding / 嵌入模型

```yaml
embedding:
  primary:
    provider: gemini               # Google direct / Google 直连
    model: models/gemini-embedding-001
    dimensions: 3072
  fallback:
    provider: openai               # Proxy / 代理
    model: gemini-embedding-001
    base_url: https://your-proxy.com/v1
    dimensions: 3072
```

## Qdrant / 向量数据库

```yaml
qdrant:
  host: localhost
  port: 6333
  collection: openclaw_memories
```

## Safety / 安全

```yaml
never_store_patterns:
  - 'sk-[A-Za-z0-9]{20,}'
  - 'password\s*[:=]\s*\S+'
  - 'token\s*[:=]\s*\S+'
  - 'cookie\s*[:=]\s*\S+'
  - '-----BEGIN\s+(RSA\s+)?PRIVATE'
```

## Quality Tier / 质量等级

```yaml
quality_tier: high
# high: Opus for consolidation, LLM for ambiguous classification
# medium: Flash for consolidation, keywords-only classification
# low: All rules-based, zero LLM calls
```

## Versioning / 版本

```yaml
schema_version: 1   # Metadata schema version / metadata 格式版本
config_version: 1   # Config file version / 配置文件版本
```
