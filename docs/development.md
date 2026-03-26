# Development Guide / 开发指南

## Project Structure / 项目结构

```
engram/
├── src/
│   ├── server.py           # MCP Server (FastMCP entry point)
│   ├── maintenance.py      # Maintenance script (daily/weekly/report)
│   ├── migrate.py          # Data migration from markdown files
│   └── engines/            # Cognitive engines
│       ├── __init__.py     # Package exports
│       ├── decay.py        # Importance decay (Bjork-enhanced)
│       ├── classifier.py   # Two-layer cascade classifier
│       ├── consolidation.py # Memory consolidation
│       └── conflict.py     # Contradiction detection & resolution
├── scripts/
│   ├── run-maintenance.sh  # Maintenance wrapper for cron
│   └── mem0-backup.sh      # Qdrant snapshot backup
├── docs/                   # Documentation
├── tests/                  # Test suite
├── config.example.yaml     # Configuration template
├── requirements.txt        # Python dependencies
└── README.md               # Project overview
```

## Key Design Decisions / 关键设计决策

### 1. Scope Isolation via Metadata / 通过 Metadata 实现 Scope 隔离

We use Mem0's custom metadata fields (stored as top-level Qdrant payload) rather than separate collections per scope. This keeps the architecture simple while enabling filtering.

使用 Mem0 的自定义 metadata 字段（存为 Qdrant payload 顶层字段）而非每个 scope 一个集合。

**Known limitation / 已知限制**: Mem0 1.0.5 + Qdrant's `AND`/`OR` composite filters are broken (GitHub #3791). We use simple key-value filters + Python post-filtering as a workaround.

### 2. infer=False for Writes / 写入时不调 LLM

Day-time `mem0_add()` uses `infer=False` — only embedding, no LLM entity extraction. This keeps write latency at ~1.3s. Entity extraction is deferred to nightly Opus maintenance.

白天写入用 `infer=False`，只做 embedding 不调 LLM（~1.3s）。Entity extraction 交给凌晨 Opus 维护。

### 3. Qdrant set_payload for Metadata Updates / 用 Qdrant 直接更新 Metadata

Mem0's `update()` only accepts text content, not metadata. For updating `access_count`, `archived`, `superseded_by`, we use `QdrantClient.set_payload()` directly. This is a partial update — other fields are preserved.

Mem0 的 `update()` 只接受文本，不支持 metadata 更新。我们用 `QdrantClient.set_payload()` 直接更新。

### 4. Embedding Model Versioning / Embedding 模型版本化

Every memory stores `embedding_model` in metadata. When switching models, old vectors can be identified and re-embedded without data loss.

每条记忆的 metadata 里存了 `embedding_model`，换模型时可识别旧向量重新嵌入。

## Adding a New Cognitive Engine / 添加新的认知引擎

1. Create `src/engines/your_engine.py`
2. Export from `src/engines/__init__.py`
3. Call from `src/maintenance.py` in the appropriate step
4. Add configuration to `config.example.yaml`
5. Write tests in `tests/test_your_engine.py`

## Adding a New Memory Type / 添加新的记忆类型

1. Add to `config.yaml` → `memory_types` section with decay and conflict rules
2. Add keyword patterns to `src/engines/classifier.py` → `KEYWORD_RULES`
3. Update documentation in `docs/usage.md`

## Adding a New Scope / 添加新的 Scope

1. Define the scope prefix convention (e.g., `project:xxx`)
2. Update search logic in `src/server.py` → `mem0_search()` if special handling needed
3. Add to `config.yaml` → agent read/write permissions
4. Update documentation

## Environment Requirements / 环境要求

- `NO_PROXY=localhost,127.0.0.1` — Required! macOS system proxy intercepts localhost HTTP requests to Qdrant. Set in MCP server env config and all scripts.

- `GOOGLE_API_KEY` — For `gemini-embedding-001`. Set in MCP server env or shell.

## Testing / 测试

```bash
cd src && python -c "
from engines import compute_importance, classify_by_keywords

# Test decay / 测试衰减
mem = {'metadata': {'mem_type': 'task_log', 'access_count': 0}, 'created_at': '2026-02-01T00:00:00+00:00'}
print('40-day task_log importance:', compute_importance(mem))

# Test classifier / 测试分类器
print('以后简约:', classify_by_keywords('以后文案都用简约风格'))
print('Gateway命令:', classify_by_keywords('Gateway 重启命令是 launchctl'))
print('好的:', classify_by_keywords('好的'))
"
```

## Contributing / 贡献

1. Fork the repo
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all existing tests pass
5. Submit a PR with clear description

Please follow the existing code style: bilingual docstrings, type hints, and structured error handling.
