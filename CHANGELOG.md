# Changelog

## v2.0.0 (2026-03-26) — "Stability & Independence"

### Breaking Changes
- Removed `config.json.example` — all configuration now in `config.yaml` + `.env`
- Environment variable `LINGYUN_GEMINI_API_KEY` replaced by `LLM_API_KEY` / `OPENAI_API_KEY`
- Data directory changed from `~/.openclaw/mem0/` to `~/.mem0-gateway/mem0/`
- Added new `llm` section in `config.yaml` for day-to-day LLM configuration
- `migrate.py` now requires `--source` flag (no longer OpenClaw-specific)

### Concurrency Safety (28 fixes)
- **Write Queue**: `fcntl.flock()` protects queue appends and replay against inode race conditions
- **Idempotent Replay**: Rename-then-process with per-entry acknowledgment — crash-safe, no duplicates
- **ENOSPC Handling**: Write queue caps at 10MB, graceful rejection on disk full
- **Maintenance Lock**: Three-layer protection (shell `flock`, Python `fcntl.flock`, `threading.Lock`)
- **Timer Safety**: `threading.Timer` with `daemon=True`, `threading.Lock` prevents re-entrancy, `try/except` with retry prevents permanent chain breakage
- **SIGTERM Handler**: Graceful shutdown on process termination
- **TOCTOU Fix**: `_safe_queue_size()` replaces racy `exists() + open()` pattern
- **Crontab Safety**: Daily maintenance restricted to Mon-Sat, preventing overlap with weekly on Sunday

### Maintenance Improvements
- **Re-extraction**: "Add-then-archive" strategy replaces "delete-then-add" — zero data loss risk
- **Stale Snapshot Fix**: Memory list refreshed after each maintenance step with graceful degradation
- **Consolidation**: Union-Find algorithm with keyword overlap for grouping, limited to 10 groups
- **Conflict Detection**: Keyword pre-filtering reduces O(n^2) LLM calls, capped at 20 pairs
- **Source Archival**: Consolidated sources marked `archived: True` with new-memory existence verification
- **Embedding Consistency**: Unified `embedding.model` reference across server and maintenance

### Code Quality
- Empty ID filtering in `_interleave`
- `_do_search` logs warnings instead of silently swallowing errors
- `mem0_search` limit bounded to `[1, 50]`
- File handle leaks fixed (`json.load(open(...))` → `with open(...)`)
- Deprecated `server_v3.py` marked

### Decoupling (Open Source)
- All paths abstracted via `ENGRAM_CONFIG`, `ENGRAM_HOST_CONFIG`, `ENGRAM_DATA_DIR` environment variables
- Default data directory: `~/.mem0-gateway/` (no external system dependency)
- Provider names configurable via `config.yaml` (`llm.provider_name`, `embedding.provider_name`)
- Notification via configurable webhook URL (no external CLI dependency)
- `migrate.py` accepts `--source` directory for any markdown file collection
- Python 3.9+ compatibility (`from __future__ import annotations`)

## v1.0.0 (2026-03-15) — Initial Open Source Release

- 5 MCP tools: `mem0_add`, `mem0_search`, `mem0_get_all`, `mem0_status`, `mem0_maintenance`
- Scope-based permission system with per-agent read/write/type rules
- 7 memory types with configurable decay and conflict strategies
- Bjork-enhanced decay formula with access_count suppression
- Dual-query search with cross-scope interleaving
- Write queue with offline degradation and auto-replay
- 4 cognitive engines: classifier, conflict, consolidation, decay
- Docker Compose deployment with Qdrant
- Comprehensive test suite
