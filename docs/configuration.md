# Configuration Reference

All configuration is in `config.yaml`. Copy from `config.example.yaml` to get started.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes (if using Gemini embeddings) | Google API key for `gemini-embedding-001` |
| `LLM_API_KEY` | Yes | API key for Mem0 inference and maintenance LLM |
| `OPENAI_API_KEY` | Alternative to `LLM_API_KEY` | Standard OpenAI key (used as fallback) |
| `EMBEDDING_API_KEY` | Optional | Separate key for embedding fallback provider |
| `ENGRAM_CONFIG` | Optional | Path to `config.yaml` (default: `../config.yaml` relative to `src/`) |
| `ENGRAM_HOST_CONFIG` | Optional | Path to host `config.json` for provider credentials (default: `~/.mem0-gateway/config.json`) |
| `ENGRAM_DATA_DIR` | Optional | Data directory for queues, locks, logs (default: `~/.mem0-gateway/mem0`) |

## Agent Permissions

```yaml
agents:
  main:
    read: [global, "group:*", dm, "agent:*", all, "cross:*"]
    write: [global, "group:*", dm]
    allowed_types: [preference, fact, procedure, lesson, decision, task_log, knowledge]
  worker_example:
    read: []
    write: ["agent:worker_example"]
    allowed_types: [procedure, task_log]

default_agent_policy:
  read: [global]
  write: []
  allowed_types: []
```

## LLM Configuration (new in v2)

```yaml
llm:
  model: gpt-4o-mini
  base_url: https://api.openai.com/v1
  # If using host config.json providers:
  # provider_name: your-provider
```

## Memory Types

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

## Maintenance

```yaml
maintenance:
  daily_time: "03:00"
  weekly_day: sunday
  weekly_window_minutes: 30
  dedup_auto_threshold: 0.92
  dedup_candidate_threshold: 0.85
  llm_chain:
    - default/gpt-4o
  llm_base_url: https://api.openai.com/v1
```

## Decay Parameters

```yaml
decay:
  task_log_half_life_days: 30
  procedure_half_life_days: 90
  access_count_cap: 3.0
  archive_threshold: 0.10
```

## Embedding

```yaml
embedding:
  model: models/gemini-embedding-001
  # provider_name: your-provider  # for fallback via host config
  primary:
    provider: gemini
    model: models/gemini-embedding-001
    dimensions: 3072
  fallback:
    provider: openai
    model: gemini-embedding-001
    base_url: https://your-proxy.com/v1
    dimensions: 3072
```

## Qdrant

```yaml
qdrant:
  host: localhost     # or "qdrant" in Docker Compose
  port: 6333
  collection: memories
```

## Safety

```yaml
never_store_patterns:
  - 'sk-[A-Za-z0-9]{20,}'
  - 'AIza[0-9A-Za-z_-]{20,}'
  - 'password\s*[:=]\s*\S+'
  - 'token\s*[:=]\s*\S+'
  - 'cookie\s*[:=]\s*\S+'
  - '-----BEGIN\s+(RSA\s+)?PRIVATE'
```

## Notification (new in v2)

```yaml
notification:
  webhook_url: https://hooks.slack.com/services/xxx/yyy/zzz
```

Maintenance reports and alerts are sent as JSON POST to this URL. Compatible with Slack, Feishu, Discord, or any webhook receiver.

## Quality Tier

```yaml
quality_tier: high
# high: Opus for consolidation, LLM for ambiguous classification
# medium: Flash for consolidation, keywords-only classification
# low: All rules-based, zero LLM calls
```

## Versioning

```yaml
schema_version: 1
config_version: 2     # Bumped in v2.0.0
```
