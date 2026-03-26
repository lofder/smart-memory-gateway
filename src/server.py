from __future__ import annotations
"""Mem0 Smart Memory Gateway v3 — MCP Server.

Scope-aware memory with provenance tracking, permission enforcement,
degradation strategy, and Qdrant-level metadata management.
"""
import fcntl, json, logging, os, re, sys, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("mem0-gateway")

os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

import yaml
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient

CONFIG_PATH = Path(os.environ.get(
    "ENGRAM_CONFIG",
    Path(__file__).parent.parent / "config.yaml",
))
HOST_CONFIG_PATH = Path(os.environ.get(
    "ENGRAM_HOST_CONFIG",
    Path.home() / ".mem0-gateway" / "config.json",
))
_DATA_DIR = Path(os.environ.get(
    "ENGRAM_DATA_DIR",
    Path.home() / ".mem0-gateway" / "mem0",
))
WRITE_QUEUE_PATH = _DATA_DIR / "write_queue.jsonl"
QUEUE_LOCK_PATH = _DATA_DIR / ".write_queue.lock"
WRITE_QUEUE_PROCESSING = WRITE_QUEUE_PATH.with_suffix(".processing.jsonl")
MAX_REPLAY_BATCH = 20
MAX_REPLAY_SECONDS = 15
ENV_PATHS = [
    Path.home() / ".mem0-gateway" / ".env",
    Path.home() / ".mem0-gateway" / ".env.main",
]
ENV_PLACEHOLDER_RE = re.compile(r"^\$\{([^}]+)\}$")

with open(CONFIG_PATH) as f:
    CFG = yaml.safe_load(f)

NEVER_STORE = [re.compile(p) for p in CFG.get("never_store_patterns", [])]
DEFAULT_USER_ID = CFG.get("default_user_id", "default")
SEARCH_ONLY_SCOPES = ("all",)
SEARCH_ONLY_PREFIXES = ("cross:",)
TOP_LEVEL_PAYLOAD_KEYS = {"data", "hash", "created_at", "updated_at", "user_id"}

_memory = None
_qdrant = None
_init_error = None
_emb_fallback_config = None
_ready = threading.Event()


def _load_env_layers():
    for env_path in ENV_PATHS:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


def _resolve_env_placeholder(value):
    if not isinstance(value, str):
        return value
    match = ENV_PLACEHOLDER_RE.fullmatch(value.strip())
    if match:
        return os.environ.get(match.group(1), value)
    return value


def _normalize_openai_base_url(value, default):
    base_url = (_resolve_env_placeholder(value) or default).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def _resolved_provider(oc, provider_name):
    provider = dict(oc.get("models", {}).get("providers", {}).get(provider_name, {}))
    if not provider:
        return {}
    if "apiKey" in provider:
        provider["apiKey"] = _resolve_env_placeholder(provider.get("apiKey"))
    if "baseUrl" in provider:
        provider["baseUrl"] = _resolve_env_placeholder(provider.get("baseUrl"))
    return provider


def _build_primary_embedder_config(emb_primary):
    config = {
        "provider": emb_primary["provider"],
        "config": {
            "model": emb_primary["model"],
            "embedding_dims": emb_primary["dimensions"],
        },
    }
    if emb_primary["provider"] == "gemini":
        api_key = (
            os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_VERTEX_API_KEY")
        )
        if api_key:
            config["config"]["api_key"] = api_key
    elif emb_primary["provider"] == "openai":
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMBEDDING_API_KEY")
        if api_key:
            config["config"]["api_key"] = api_key
        base_url = emb_primary.get("base_url")
        if base_url:
            config["config"]["openai_base_url"] = base_url
    return config


def _build_fallback_embedder_config(emb_fallback, provider):
    api_key = provider.get("apiKey") or os.environ.get("EMBEDDING_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return {
        "provider": "openai",
        "config": {
            "model": emb_fallback["model"],
            "openai_base_url": _normalize_openai_base_url(
                provider.get("baseUrl") or emb_fallback["base_url"],
                emb_fallback["base_url"],
            ),
            "api_key": api_key,
            "embedding_dims": emb_fallback["dimensions"],
        },
    }


def _init_backends():
    global _memory, _qdrant, _init_error
    try:
        from mem0 import Memory
        _load_env_layers()
        if HOST_CONFIG_PATH.exists():
            with open(HOST_CONFIG_PATH) as _hc:
                oc = json.load(_hc)
        else:
            oc = {}
            sys.stderr.write(f"engram: {HOST_CONFIG_PATH} not found, using env vars only\n")
        emb_primary = CFG["embedding"]["primary"]
        emb_fallback = CFG["embedding"]["fallback"]
        q_cfg = CFG["qdrant"]
        llm_cfg = CFG.get("llm", {})
        llm_provider_name = llm_cfg.get("provider_name", "default")
        llm_provider = _resolved_provider(oc, llm_provider_name) if oc else {}

        embedder_cfg_name = CFG["embedding"].get("provider_name", "default")
        emb_provider = _resolved_provider(oc, embedder_cfg_name) if oc else {}

        embedder_config = _build_primary_embedder_config(emb_primary)
        global _emb_fallback_config
        _emb_fallback_config = _build_fallback_embedder_config(emb_fallback, emb_provider)

        llm_api_key = (
            llm_provider.get("apiKey")
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        llm_base_url = _normalize_openai_base_url(
            llm_provider.get("baseUrl") or llm_cfg.get("base_url", ""),
            llm_cfg.get("base_url", "https://api.openai.com/v1"),
        )

        mem_config = {
            "vector_store": {"provider": "qdrant", "config": {
                "collection_name": q_cfg["collection"],
                "host": q_cfg["host"],
                "port": q_cfg["port"],
            }},
            "llm": {"provider": "openai", "config": {
                "model": llm_cfg.get("model", "gpt-4o-mini"),
                "api_key": llm_api_key,
                "openai_base_url": llm_base_url,
            }},
            "embedder": embedder_config,
            "version": "v1.1",
        }
        try:
            _memory = Memory.from_config(mem_config)
        except Exception as primary_error:
            if not _emb_fallback_config:
                raise
            fallback_config = dict(mem_config)
            fallback_config["embedder"] = _emb_fallback_config
            try:
                _memory = Memory.from_config(fallback_config)
                sys.stderr.write(
                    f"mem0-gateway: primary embedder failed, using fallback: {primary_error}\n"
                )
            except Exception as fallback_error:
                raise RuntimeError(
                    f"primary embedder failed: {primary_error}; fallback embedder failed: {fallback_error}"
                ) from fallback_error
        _qdrant = QdrantClient(host=q_cfg["host"], port=q_cfg["port"])
        sys.stderr.write(f"mem0-gateway: initialized OK\n")
        # Start async replay timer after successful init
        try:
            _replay_write_queue(_memory)
        except Exception:
            pass
        _schedule_next_timer()
    except Exception as e:
        _init_error = str(e)
        sys.stderr.write(f"mem0-gateway: init FAILED: {e}\n")
    finally:
        _ready.set()


threading.Thread(target=_init_backends, daemon=True).start()

# --- Phase 3: Async replay timer + graceful shutdown ---
_replay_lock = threading.Lock()
_shutdown = threading.Event()


def _schedule_next_timer():
    """Schedule next replay timer. try/except prevents permanent chain breakage."""
    if _shutdown.is_set():
        return
    try:
        t = threading.Timer(60, _replay_timer_callback)
        t.daemon = True
        t.start()
    except Exception as e:
        sys.stderr.write(f"mem0-gateway: timer schedule failed: {e}\n")
        try:
            time.sleep(5)
            t = threading.Timer(60, _replay_timer_callback)
            t.daemon = True
            t.start()
        except Exception:
            sys.stderr.write("mem0-gateway: CRITICAL: replay timer permanently broken\n")


def _replay_timer_callback():
    if not _replay_lock.acquire(blocking=False):
        _schedule_next_timer()
        return
    try:
        mem, _ = _get_backends()
        if mem:
            _replay_write_queue(mem)
    except Exception as e:
        sys.stderr.write(f"mem0-gateway: replay timer error: {e}\n")
    finally:
        _replay_lock.release()
        _schedule_next_timer()


def _handle_sigterm(signum, frame):
    _shutdown.set()
    sys.stderr.write("mem0-gateway: SIGTERM received, shutting down\n")
    sys.exit(0)


import signal
signal.signal(signal.SIGTERM, _handle_sigterm)
# --- End Phase 3 infrastructure ---


mcp = FastMCP("engram")


def _get_backends():
    _ready.wait(timeout=30)
    return _memory, _qdrant


def _point_to_memory_item(point):
    payload = dict(point.payload or {})
    metadata = {
        key: value
        for key, value in payload.items()
        if key not in TOP_LEVEL_PAYLOAD_KEYS
    }
    return {
        "id": str(point.id),
        "memory": payload.get("data", ""),
        "hash": payload.get("hash", ""),
        "metadata": metadata,
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "user_id": payload.get("user_id"),
    }


def _load_all_memories_from_qdrant(qc, user_id=None, scope="", include_archived=True):
    user_id = user_id or DEFAULT_USER_ID
    collection = CFG["qdrant"]["collection"]
    offset = None
    items = []

    while True:
        points, offset = qc.scroll(
            collection_name=collection,
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=offset,
            timeout=60,
        )
        for point in points:
            payload = point.payload or {}
            if user_id and payload.get("user_id") != user_id:
                continue
            if scope and payload.get("scope") != scope:
                continue
            if not include_archived and payload.get("archived", False):
                continue
            items.append(_point_to_memory_item(point))
        if offset is None:
            break

    items.sort(key=lambda item: ((item.get("created_at") or ""), item.get("id") or ""))
    return items


def _check_permission(agent: str, action: str, scope: str, mem_type: str) -> str | None:
    agents_cfg = CFG.get("agents", {})
    policy = agents_cfg.get(agent, CFG.get("default_agent_policy", {}))

    if action == "write":
        allowed_scopes = policy.get("write", [])
        allowed_types = policy.get("allowed_types", [])
        if not _scope_matches(scope, allowed_scopes):
            return f"Agent '{agent}' cannot write to scope '{scope}'"
        if mem_type and mem_type not in allowed_types:
            return f"Agent '{agent}' cannot write mem_type '{mem_type}'"
    elif action == "read":
        allowed_scopes = policy.get("read", [])
        if not _scope_matches(scope, allowed_scopes):
            return f"Agent '{agent}' cannot read scope '{scope}'"
    return None


def _scope_matches(scope: str, allowed: list) -> bool:
    if not allowed:
        return False
    for pattern in allowed:
        if pattern == scope:
            return True
        if pattern.endswith(":*") and scope.startswith(pattern[:-1]):
            return True
        if pattern == "all" and scope == "all":
            return True
    return False


def _check_never_store(content: str) -> str | None:
    for pat in NEVER_STORE:
        if pat.search(content):
            return "Content contains sensitive credentials. Store a summary instead."
    return None


def _do_search(mem, query, filters, limit):
    try:
        results = mem.search(query, user_id=DEFAULT_USER_ID, limit=limit, filters=filters or None)
        items = results if isinstance(results, list) else results.get("results", [])
        return items
    except Exception as e:
        logger.warning("mem0_search failed: %s", e)
        return []


def _safe_queue_size():
    """Read write queue size with TOCTOU protection."""
    try:
        if WRITE_QUEUE_PATH.exists():
            return sum(1 for _ in open(WRITE_QUEUE_PATH))
        return 0
    except (FileNotFoundError, OSError):
        return 0


def _interleave(scoped, global_items, limit):
    seen = set()
    merged = []
    sources = [(scoped, "scoped"), (global_items, "global")]
    for items, _ in sources:
        for item in sorted(items, key=lambda x: (
            {"high": 2, "medium": 1, "low": 0}.get(x.get("metadata", {}).get("trust", "medium"), 1),
            x.get("score", 0),
        ), reverse=True):
            mid = item.get("id", "")
            if mid and mid not in seen:
                seen.add(mid)
                merged.append(item)
    return merged[:limit]



def _acquire_queue_lock(blocking=False, timeout_s=1):
    """Acquire queue lock. Non-blocking by default for replay; short-timeout blocking for append."""
    QUEUE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(QUEUE_LOCK_PATH), os.O_CREAT | os.O_WRONLY, 0o644)
    if not blocking:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except (BlockingIOError, OSError):
            os.close(fd)
            return -1
    else:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                time.sleep(0.05)
        os.close(fd)
        return -1


def _release_queue_lock(fd):
    if fd >= 0:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except OSError:
            pass


def _safe_queue_append(entry: dict):
    """Append entry to write queue with flock protection against inode race."""
    try:
        data = json.dumps(entry, ensure_ascii=False) + "\n"
    except (TypeError, ValueError):
        return
    fd = _acquire_queue_lock(blocking=True, timeout_s=1)
    if fd < 0:
        sys.stderr.write("mem0-gateway: queue lock timeout, dropping entry\n")
        return
    try:
        WRITE_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            if WRITE_QUEUE_PATH.exists() and WRITE_QUEUE_PATH.stat().st_size > 10_000_000:
                sys.stderr.write("mem0-gateway: write queue full (10MB), dropping entry\n")
                return
        except OSError:
            pass
        try:
            with open(WRITE_QUEUE_PATH, "a") as f:
                f.write(data)
        except OSError as e:
            sys.stderr.write(f"mem0-gateway: queue append failed: {e}\n")
    finally:
        _release_queue_lock(fd)


def _replay_write_queue(mem):
    """Replay queued writes with flock, rename-then-process, and per-entry ack."""
    if not WRITE_QUEUE_PATH.exists() and not WRITE_QUEUE_PROCESSING.exists():
        return
    fd = _acquire_queue_lock(blocking=False)
    if fd < 0:
        return

    try:
        # Crash recovery: merge leftover .processing back into queue
        if WRITE_QUEUE_PROCESSING.exists():
            try:
                data = WRITE_QUEUE_PROCESSING.read_text()
                if data.strip():
                    with open(WRITE_QUEUE_PATH, "a") as f:
                        f.write(data if data.endswith("\n") else data + "\n")
                WRITE_QUEUE_PROCESSING.unlink(missing_ok=True)
            except (FileNotFoundError, OSError):
                pass

        if not WRITE_QUEUE_PATH.exists():
            return

        # Atomic rename under lock
        try:
            WRITE_QUEUE_PATH.rename(WRITE_QUEUE_PROCESSING)
        except (FileNotFoundError, OSError):
            return

        # Release lock so agents can create new queue file
        _release_queue_lock(fd)
        fd = -1

        # Process .processing file
        remaining, replayed, t0 = [], 0, time.monotonic()
        try:
            all_lines = [l for l in WRITE_QUEUE_PROCESSING.read_text().strip().split("\n") if l.strip()]
        except (FileNotFoundError, OSError):
            return

        for i, line in enumerate(all_lines):
            if replayed >= MAX_REPLAY_BATCH or (time.monotonic() - t0) > MAX_REPLAY_SECONDS:
                remaining.extend(all_lines[i:])
                break
            try:
                entry = json.loads(line)
                mem.add(entry["content"], user_id=DEFAULT_USER_ID, metadata=entry["metadata"])
                replayed += 1
                # Per-entry ack: truncate .processing to remaining lines
                try:
                    rest = all_lines[i+1:]
                    if rest:
                        WRITE_QUEUE_PROCESSING.write_text("\n".join(r for r in rest if r.strip()) + "\n")
                    else:
                        WRITE_QUEUE_PROCESSING.unlink(missing_ok=True)
                except OSError:
                    pass
            except json.JSONDecodeError:
                pass
            except Exception:
                remaining.append(line)

        # Put remaining entries back into queue (re-acquire lock)
        if remaining:
            fd2 = _acquire_queue_lock(blocking=True, timeout_s=2)
            try:
                with open(WRITE_QUEUE_PATH, "a") as f:
                    f.write("\n".join(r for r in remaining if r.strip()) + "\n")
            except OSError as e:
                sys.stderr.write(f"mem0-gateway: failed to write back remaining: {e}\n")
            finally:
                _release_queue_lock(fd2)
        WRITE_QUEUE_PROCESSING.unlink(missing_ok=True)

        if replayed:
            sys.stderr.write(f"mem0-gateway: replayed {replayed} queued writes\n")
    finally:
        _release_queue_lock(fd)


def _bump_access_count(qc, collection, ids):
    for mid in ids:
        try:
            pts = qc.retrieve(collection_name=collection, ids=[mid], with_payload=True)
            if not pts:
                qc.set_payload(collection, payload={"access_count": 1}, points=[mid])
                continue
            current = (pts[0].payload or {}).get("access_count", 0)
            qc.set_payload(collection, payload={"access_count": current + 1}, points=[mid])
        except Exception:
            pass


@mcp.tool()
def mem0_add(content: str, scope: str = "", context: str = "",
             source: str = "agent_output", trust: str = "medium",
             mem_type: str = "", agent: str = "main") -> str:
    """Add a memory with structured provenance and scope isolation."""
    if not scope:
        return json.dumps({"error": "scope is required. Use global/group:oc_xxx/dm/agent:xxx"})

    if scope in SEARCH_ONLY_SCOPES or any(scope.startswith(p) for p in SEARCH_ONLY_PREFIXES):
        return json.dumps({"error": f"scope '{scope}' is search-only, cannot write"})

    perm_err = _check_permission(agent, "write", scope, mem_type)
    if perm_err:
        return json.dumps({"error": perm_err})

    cred_err = _check_never_store(content)
    if cred_err:
        return json.dumps({"error": cred_err})

    mem, qc = _get_backends()
    metadata = {
        "scope": scope,
        "source": source,
        "trust": trust,
        "mem_type": mem_type,
        "agent": agent,
        "context": context,
        "access_count": 0,
        "archived": False,
        "embedding_model": CFG["embedding"]["model"],
        "schema_version": CFG["schema_version"],
    }

    if mem is None:
        write_id = str(uuid.uuid4())
        entry = {"write_id": write_id, "content": content, "metadata": metadata, "ts": datetime.now(timezone.utc).isoformat()}
        _safe_queue_append(entry)
        return json.dumps({"queued": True, "write_id": write_id, "reason": "Mem0 unavailable, cached for replay"})

    try:
        result = mem.add(content, user_id=DEFAULT_USER_ID, metadata=metadata, infer=False)
        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        write_id = str(uuid.uuid4())
        entry = {"write_id": write_id, "content": content, "metadata": metadata, "ts": datetime.now(timezone.utc).isoformat()}
        _safe_queue_append(entry)
        return json.dumps({"queued": True, "write_id": write_id, "error": str(e)})


@mcp.tool()
def mem0_search(query: str, scope: str = "global", mem_type: str = "",
                trust_min: str = "", limit: int = 5, agent: str = "main") -> str:
    """Search memories with scope isolation and dual-query merge."""
    perm_err = _check_permission(agent, "read", scope, "")
    if perm_err:
        return json.dumps({"error": perm_err})

    limit = max(1, min(limit, 50))
    mem, qc = _get_backends()
    if mem is None:
        return json.dumps({"results": [], "degraded": True, "reason": _init_error or "Mem0 unavailable"})

    base_filters = {"archived": False}
    if mem_type:
        base_filters["mem_type"] = mem_type

    collection = CFG["qdrant"]["collection"]

    try:
        if scope == "all":
            items = _do_search(mem, query, base_filters or None, limit * 2)
        elif scope.startswith("cross:"):
            target = scope.replace("cross:", "group:")
            global_items = _do_search(mem, query, {**base_filters, "scope": "global"}, limit)
            cross_items = _do_search(mem, query, {**base_filters, "scope": target}, limit)
            items = _interleave(cross_items, global_items, limit)
        elif scope == "global":
            items = _do_search(mem, query, {**base_filters, "scope": "global"}, limit)
        else:
            global_items = _do_search(mem, query, {**base_filters, "scope": "global"}, limit)
            scoped_items = _do_search(mem, query, {**base_filters, "scope": scope}, limit)
            items = _interleave(scoped_items, global_items, limit)

        if trust_min:
            trust_order = {"high": 3, "medium": 2, "low": 1}
            min_level = trust_order.get(trust_min, 0)
            items = [i for i in items if trust_order.get(
                i.get("metadata", {}).get("trust", "medium"), 2) >= min_level]

        items = [i for i in items if not i.get("metadata", {}).get("archived", False)]

        result_ids = [i.get("id") for i in items[:limit] if i.get("id")]
        if result_ids and qc:
            threading.Thread(target=_bump_access_count, args=(qc, collection, result_ids), daemon=True).start()

        return json.dumps(items[:limit], default=str, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"results": [], "degraded": True, "error": str(e)})


@mcp.tool()
def mem0_get_all(user_id: str = "main", scope: str = "", agent: str = "main") -> str:
    """Get all memories, optionally filtered by scope."""
    effective_scope = scope if scope else "all"
    perm_err = _check_permission(agent, "read", effective_scope, "")
    if perm_err:
        logger.warning("AUDIT: %s get_all denied scope=%s: %s", agent, effective_scope, perm_err)
    mem, qc = _get_backends()
    if mem is None and qc is None:
        return json.dumps({"error": "Mem0 unavailable"})
    try:
        if qc is not None:
            items = _load_all_memories_from_qdrant(qc, user_id=user_id, scope=scope, include_archived=False)
        else:
            filters = {}
            if scope:
                filters["scope"] = scope
            all_mem = mem.get_all(user_id=user_id, filters=filters or None)
            items = all_mem if isinstance(all_mem, list) else all_mem.get("results", [])
            items = [i for i in items if not i.get("metadata", {}).get("archived", False)]
        return json.dumps({"total": len(items), "results": items}, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mem0_status(agent: str = "main") -> str:
    """Health check: total memories, scope/type distribution, Qdrant status."""
    mem, qc = _get_backends()
    status = {
        "mem0_ready": mem is not None,
        "qdrant_ready": qc is not None,
        "init_error": _init_error,
    }
    if mem is None and qc is None:
        return json.dumps(status)

    try:
        sdk_count = None
        if mem is not None:
            all_mem = mem.get_all(user_id=DEFAULT_USER_ID)
            sdk_items = all_mem if isinstance(all_mem, list) else all_mem.get("results", [])
            sdk_count = len(sdk_items)

        if qc is not None:
            items = _load_all_memories_from_qdrant(qc, user_id=DEFAULT_USER_ID, include_archived=True)
            status["inventory_source"] = "qdrant_scroll"
        else:
            items = sdk_items
            status["inventory_source"] = "mem_get_all"

        by_scope, by_type, by_trust = {}, {}, {}
        active = 0
        for item in items:
            meta = item.get("metadata", {})
            if meta.get("archived"):
                continue
            active += 1
            s = meta.get("scope", "unknown")
            t = meta.get("mem_type", "unknown")
            tr = meta.get("trust", "unknown")
            by_scope[s] = by_scope.get(s, 0) + 1
            by_type[t] = by_type.get(t, 0) + 1
            by_trust[tr] = by_trust.get(tr, 0) + 1

        status.update({
            "total_memories": len(items),
            "active_memories": active,
            "archived_memories": len(items) - active,
            "by_scope": by_scope,
            "by_type": by_type,
            "by_trust": by_trust,
            "write_queue_size": _safe_queue_size(),
            "config_version": CFG.get("config_version"),
            "schema_version": CFG.get("schema_version"),
            "embedding_model": CFG["embedding"]["model"],
        })
        if sdk_count is not None:
            status["sdk_get_all_count"] = sdk_count
            status["sdk_get_all_truncated"] = sdk_count < len(items)
    except Exception as e:
        status["error"] = str(e)

    return json.dumps(status, default=str, ensure_ascii=False)


@mcp.tool()
def mem0_maintenance(mode: str = "daily", agent: str = "main") -> str:
    """Run memory maintenance. mode: daily/weekly/report_only.
    daily: Opus re-extract today's memories + dedup + report.
    weekly: daily + consolidation + conflict detection + decay + timeline.
    report_only: generate status report without any changes.
    """
    perm_err = _check_permission(agent, "write", "global", "")
    if perm_err and mode != "report_only":
        return json.dumps({"error": f"Only main/devops/monitor can trigger maintenance. {perm_err}"})

    mem, qc = _get_backends()
    if mem is None:
        return json.dumps({"error": "Mem0 unavailable"})

    report = {"mode": mode, "started_at": datetime.now(timezone.utc).isoformat(), "triggered_by": agent}

    try:
        if mode == "report_only":
            status = json.loads(mem0_status(agent=agent))
            report.update(status)
        elif mode in ("daily", "weekly"):
            report["message"] = f"{mode} maintenance placeholder - full implementation in Phase 4"
            report["status"] = "not_yet_implemented"
        else:
            return json.dumps({"error": f"Unknown mode: {mode}. Use daily/weekly/report_only"})

        report["completed_at"] = datetime.now(timezone.utc).isoformat()

        webhook_url = CFG.get("notification", {}).get("webhook_url", "")
        if webhook_url:
            def _send_webhook():
                try:
                    import urllib.request
                    body = json.dumps({"text": json.dumps(report, ensure_ascii=False, indent=2, default=str)[:2000]}).encode()
                    req = urllib.request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=15)
                except Exception:
                    pass
            threading.Thread(target=_send_webhook, daemon=True).start()

        return json.dumps(report, default=str, ensure_ascii=False)

    except Exception as e:
        report["error"] = str(e)
        return json.dumps(report, default=str, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
