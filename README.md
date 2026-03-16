# Smart Memory Gateway

> Scope-aware memory architecture for multi-agent AI assistants, powered by Mem0 + Qdrant + MCP.

A production-grade memory system that gives AI agents persistent, structured memory with group-chat isolation, provenance tracking, neuroscience-inspired maintenance, and configurable access control.

## Features

- **Scope Isolation** — Memories are scoped to `global`, `group`, `dm`, or `agent` namespaces. Group A's data never leaks to Group B.
- **Dual-Query Search** — Automatically merges global context with current scope results in every search.
- **Structured Provenance** — Every memory carries `source`, `trust_level`, `scope`, `mem_type`, and `agent` metadata.
- **Cognitive Engines** — Decay (Bjork-inspired), consolidation, conflict detection, and cascade classification.
- **Automated Maintenance** — Daily Opus re-extraction + dedup; weekly consolidation + conflict resolution + decay.
- **Credential Safety** — Regex-based `never_store` rules block passwords, API keys, and tokens from being memorized.
- **Graceful Degradation** — 3-level fallback: embedding API → Qdrant Server → MCP Server, with write queue replay.
- **Config-Driven** — All permissions, decay parameters, and maintenance schedules in one `config.yaml`.
- **MCP Standard** — Runs as a FastMCP server, compatible with any MCP-enabled AI framework.

## Quick Start

### Prerequisites

- Python 3.11+
- Qdrant Server ([download](https://github.com/qdrant/qdrant/releases))
- Google API Key (for `gemini-embedding-001`) or OpenAI-compatible embedding provider

### Install

```bash
pip install mem0ai qdrant-client mcp pyyaml
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
Agent Layer          MCP Server (FastMCP)         Storage Layer
┌─────────┐         ┌──────────────────┐         ┌─────────────┐
│  Main   │────────▶│  mem0_add        │────────▶│  Mem0 1.0.5 │
│  Agent  │◀────────│  mem0_search     │◀────────│      +      │
│         │         │  mem0_status     │         │  Qdrant     │
├─────────┤         │  mem0_maintenance│         │  Server     │
│ Workers │───────▶ │  mem0_get_all    │         └─────────────┘
│(limited)│         └──────────────────┘                │
└─────────┘                  │                   ┌──────┴──────┐
                    ┌────────┴────────┐          │  Cognitive  │
                    │  Permission     │          │  Engines    │
                    │  Enforcement    │          │  (decay,    │
                    │  + Degradation  │          │  classify,  │
                    │  + Never-Store  │          │  consolidate│
                    └─────────────────┘          │  conflict)  │
                                                 └─────────────┘
```

## Documentation

- [Design Document (中文)](docs/design_cn.md) — Full 9-chapter system design
- [Usage Guide](docs/usage.md) — How to integrate with your AI agent
- [Development Guide](docs/development.md) — How to extend and contribute
- [Configuration Reference](docs/configuration.md) — All config.yaml options

## Academic Foundation

This system's design is informed by 8 peer-reviewed papers and 4 production case studies:

| Paper | Key Insight | Our Application |
|-------|-------------|-----------------|
| Hindsight (2512.12818) | 4-network memory, 91.4% accuracy | fact/preference/knowledge/log classification |
| MAPLE (2602.13258) | HOT/COLD path separation | Async write, sync read |
| FadeMem (2601.18642) | Importance-based decay, -45% storage | Bjork-enhanced decay formula |
| OWASP ASI06 (2026) | Memory poisoning risk 40%→80% | trust_level + never_store |
| Bjork (1992) | Storage-retrieval strength theory | access_count in decay formula |

## License

MIT — See [LICENSE](LICENSE)

## Contributing

Issues and PRs welcome. Please read [docs/development.md](docs/development.md) first.
