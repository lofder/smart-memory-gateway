# Smart Memory Gateway

> Scope-aware memory architecture for multi-agent AI assistants, powered by Mem0 + Qdrant + MCP.

A production-grade memory system that gives AI agents persistent, structured memory with group-chat isolation, provenance tracking, neuroscience-inspired maintenance, and configurable access control.

### Design Goals

1. **Maximize agent autonomy** — Agents decide what to remember and when to recall, no human intervention needed
2. **Minimize token usage** — Dual-query merging, trust-based ranking, dedup, consolidation, and decay keep context lean
3. **Truly persistent memory** — User profile memories never decay; operational logs consolidate into permanent knowledge

## Features

- **Scope Isolation** — Memories are scoped to `global`, `group`, `dm`, or `agent` namespaces. Group A's data never leaks to Group B.
- **Dual-Query Search** — Automatically merges global context with current scope results in every search.
- **Structured Provenance** — Every memory carries `source`, `trust`, `scope`, `mem_type`, and `agent` metadata.
- **Cognitive Engines** — Decay (Bjork-inspired), consolidation, conflict detection, and cascade classification.
- **Scheduled Maintenance** — Daily Opus re-extraction + dedup; weekly consolidation + conflict resolution + decay. Runs via CLI + cron (see [Maintenance](#maintenance)).
- **Credential Safety** — Regex-based `never_store` rules block passwords, API keys, and tokens from being memorized.
- **Graceful Degradation** — Embedding primary/fallback switching + write queue replay when Mem0 is unavailable.
- **Config-Driven** — All permissions, decay parameters, and maintenance schedules in one `config.yaml`.
- **MCP Standard** — Runs as a FastMCP server, compatible with any MCP-enabled AI framework.

## Quick Start

### Prerequisites

- Python 3.11+
- Qdrant Server ([download](https://github.com/qdrant/qdrant/releases))
- Google API Key (for `gemini-embedding-001`) or OpenAI-compatible embedding provider

### Install

```bash
pip install mem0ai qdrant-client mcp pyyaml pydantic
```

### Configure

```bash
cp config.example.yaml config.yaml
# Edit config.yaml: set your API keys, Qdrant host, agent permissions
```

### Run

```bash
# Start Qdrant Server
./qdrant --config-path qdrant-config.yaml &

# Start MCP Server
python src/server.py
```

### Use (from your AI agent)

```python
# Search memories
mcp(action="call", server="mem0", tool="mem0_search",
    args={"query": "user preferences", "scope": "group:my_group", "limit": 5})

# Add a memory
mcp(action="call", server="mem0", tool="mem0_add",
    args={"content": "User prefers minimal style", "scope": "global",
          "mem_type": "preference", "source": "user_direct", "trust": "high"})

# Check health
mcp(action="call", server="mem0", tool="mem0_status", args={})
```

## Architecture

```
                 ┌──────────────────────────────┐
                 │     Agent Layer (L1)          │
                 │  Main: read all, write global │
                 │  Workers: write agent:{self}  │
                 └──────────┬───────────────────┘
                            │ MCP (stdio)
                 ┌──────────▼───────────────────┐
                 │  Smart Memory Gateway (L2)    │
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

### Memory Lifecycle

| Type | Decay | Purpose |
|------|-------|---------|
| `preference` / `fact` | Never | User profile — persists forever |
| `lesson` / `decision` | Never | Experience — persists forever |
| `knowledge` | Never | Consolidated from task_logs |
| `procedure` | 90-day half-life | SOPs, commands |
| `task_log` | 30-day half-life | Operational logs → consolidated before decay |

### Maintenance

Maintenance runs as a separate CLI process, scheduled via cron:

```cron
15 2 * * * /path/to/scripts/mem0-backup.sh          # Daily backup
 0 3 * * * /path/to/scripts/run-maintenance.sh daily  # Opus re-extract + dedup
 0 4 * * 0 /path/to/scripts/run-maintenance.sh weekly # + conflict + consolidate + decay
```

The `mem0_maintenance` MCP tool provides maintenance reports and status; the actual maintenance pipeline runs via `python src/maintenance.py`.

## Documentation

- [Architecture v2](ARCHITECTURE-v2.md) — Full architecture document with three design goals analysis
- [Design Document (中文)](docs/design_cn.md) — Full 9-chapter system design
- [Usage Guide](docs/usage.md) — How to integrate with your AI agent
- [Development Guide](docs/development.md) — How to extend and contribute
- [Configuration Reference](docs/configuration.md) — All config.yaml options

## Academic Foundation

This system's design is informed by peer-reviewed research:

| Paper | Key Insight | Our Application |
|-------|-------------|-----------------|
| Hindsight (2512.12818) | 4-network memory, 91.4% accuracy | 7 memory type classification |
| MAPLE (2602.13258) | HOT/COLD path separation | Daytime fast write (`infer=False`) + nightly Opus deep processing |
| FadeMem (2601.18642) | Importance-based decay, -45% storage | Bjork-enhanced decay formula |
| OWASP ASI06 (2026) | Memory poisoning risk 40%→80% | trust + never_store + scope isolation |
| Bjork (1992) | Storage-retrieval strength theory | access_count suppresses decay |
| TierMem (2602.17913) | Provenance tracking reduces token | Structured metadata per memory |

## License

MIT — See [LICENSE](LICENSE)

## Contributing

Issues and PRs welcome. Please read [docs/development.md](docs/development.md) first.
