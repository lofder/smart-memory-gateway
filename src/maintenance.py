#!/usr/bin/env python3
"""Memory maintenance script for Smart Memory Gateway v3.
记忆维护脚本 — 智能记忆网关 v3。

Usage / 用法:
    python3 maintenance.py --mode daily        # Opus re-extract + dedup + report / Opus 重提取 + 去重 + 报告
    python3 maintenance.py --mode weekly       # daily + consolidation + conflict + decay / 每日 + 巩固 + 冲突 + 衰减
    python3 maintenance.py --mode report_only  # Just report, no changes / 仅报告，不做修改

Designed to be called by cron or manually via MCP tool.
设计为由 cron 自动触发或通过 MCP 工具手动调用。
"""
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

sys.path.insert(0, str(Path(__file__).parent))

import yaml
from mem0 import Memory
from qdrant_client import QdrantClient

CONFIG_PATH = Path(__file__).parent / "config.yaml"
HOST_CONFIG_PATH = Path.home() / ".mem0-gateway" / "config.json"
PLAN_DIR = Path.home() / ".mem0-gateway" / "mem0" / "maintenance_plans"
REPORT_DIR = Path.home() / ".mem0-gateway" / "mem0" / "maintenance_reports"
ENV_PATHS = [
    Path.home() / ".mem0-gateway" / ".env",
    Path.home() / ".mem0-gateway" / ".env.main",
]
ENV_PLACEHOLDER_RE = re.compile(r"^\$\{([^}]+)\}$")

with open(CONFIG_PATH) as f:
    CFG = yaml.safe_load(f)

TOP_LEVEL_PAYLOAD_KEYS = {"data", "hash", "created_at", "updated_at", "user_id"}


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


def _build_primary_embedder_config():
    emb_primary = CFG["embedding"]["primary"]
    config = {
        "provider": emb_primary["provider"],
        "config": {
            "model": f"models/{emb_primary['model'].split('/')[-1]}",
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
    return config


def _build_fallback_embedder_config(oc):
    emb_fallback = CFG["embedding"]["fallback"]
    provider = _resolved_provider(oc, "lingyun-gemini")
    api_key = provider.get("apiKey") or os.environ.get("LINGYUN_GEMINI_API_KEY")
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


def _make_memory_with_embedder_fallback(oc, llm_config):
    base_config = {
        "vector_store": {"provider": "qdrant", "config": {
            "collection_name": CFG["qdrant"]["collection"],
            "host": CFG["qdrant"]["host"],
            "port": CFG["qdrant"]["port"],
        }},
        "llm": llm_config,
        "embedder": _build_primary_embedder_config(),
        "version": "v1.1",
    }
    try:
        return Memory.from_config(base_config)
    except Exception as primary_error:
        fallback_embedder = _build_fallback_embedder_config(oc)
        if not fallback_embedder:
            raise
        fallback_config = dict(base_config)
        fallback_config["embedder"] = fallback_embedder
        try:
            return Memory.from_config(fallback_config)
        except Exception as fallback_error:
            raise RuntimeError(
                f"primary embedder failed: {primary_error}; fallback embedder failed: {fallback_error}"
            ) from fallback_error


def _make_opus_memory():
    """Create Memory instance with Opus LLM for high-quality extraction."""
    _load_env_layers()
    oc = json.load(open(HOST_CONFIG_PATH))
    llm_chain = CFG.get("maintenance", {}).get("llm_chain", [])
    model = llm_chain[0] if llm_chain else "claude-opus-4-6"
    model_name = model.split("/")[-1] if "/" in model else model
    provider_name = model.split("/")[0] if "/" in model else "your_provider"

    provider = _resolved_provider(
        oc,
        provider_name if provider_name in oc["models"]["providers"] else "your_provider",
    )

    return _make_memory_with_embedder_fallback(oc, {
        "provider": "openai",
        "config": {
            "model": model_name,
            "api_key": provider.get("apiKey"),
            "openai_base_url": _normalize_openai_base_url(
                provider.get("baseUrl"),
                "https://api.your_provider.top",
            ),
        },
    })


def _make_llm_call(oc):
    """Create a simple LLM call function using the maintenance LLM chain."""
    import urllib.request, ssl
    llm_chain = CFG.get("maintenance", {}).get("llm_chain", [])

    def call(prompt):
        for model_spec in llm_chain:
            parts = model_spec.split("/")
            provider_name = parts[0] if len(parts) > 1 else "your_provider"
            model_name = parts[-1]
            provider = _resolved_provider(oc, provider_name)
            if not provider:
                continue
            try:
                body = json.dumps({"model": model_name, "messages": [{"role": "user", "content": prompt}], "max_tokens": 500, "temperature": 0}).encode()
                base = _normalize_openai_base_url(
                    provider.get("baseUrl"),
                    "https://api.your_provider.top",
                )
                url = f"{base}/chat/completions"
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {provider['apiKey']}"})
                resp = urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context())
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
            except Exception:
                continue
        raise RuntimeError("All LLM providers failed")

    return call


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


def _load_all_memories_from_qdrant(qc, user_id="default", scope="", include_archived=True):
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


def get_all_memories(m, qc=None, user_id="default", scope="", include_archived=True):
    if qc is not None:
        return _load_all_memories_from_qdrant(qc, user_id=user_id, scope=scope, include_archived=include_archived)

    filters = {}
    if scope:
        filters["scope"] = scope
    all_mem = m.get_all(user_id=user_id, filters=filters or None)
    items = all_mem if isinstance(all_mem, list) else all_mem.get("results", [])
    if include_archived:
        return items
    return [mem for mem in items if not mem.get("metadata", {}).get("archived", False)]


def get_today_memories(memories):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = []
    for mem in memories:
        created = mem.get("created_at", "")
        if isinstance(created, str) and today in created:
            result.append(mem)
    return result


def step_opus_reextract(opus_mem, memories, report):
    """Step 1: Re-add today's memories with Opus for better entity extraction."""
    today_mems = get_today_memories(memories)
    report["re_extract_total"] = len(today_mems)
    ok, fail = 0, 0

    for mem in today_mems:
        try:
            content = mem.get("memory", "")
            metadata = mem.get("metadata", {})
            mid = mem.get("id", "")
            if not content or not mid:
                continue
            opus_mem.delete(mid)
            opus_mem.add(content, user_id="default", metadata=metadata)
            ok += 1
        except Exception as e:
            fail += 1
            report.setdefault("errors", []).append(f"re-extract {mid}: {e}")

    report["re_extract_ok"] = ok
    report["re_extract_fail"] = fail


def step_dedup(m, qc, memories, report):
    """Step 2-3: Dedup within each scope."""
    from engines.classifier import classify_by_keywords
    collection = CFG["qdrant"]["collection"]
    auto_threshold = CFG.get("maintenance", {}).get("dedup_auto_threshold", 0.92)
    auto_merged = 0

    scopes = set(mem.get("metadata", {}).get("scope", "global") for mem in memories)
    for scope in scopes:
        scope_mems = [m2 for m2 in memories if m2.get("metadata", {}).get("scope") == scope and not m2.get("metadata", {}).get("archived")]
        seen_pairs = set()
        for mem in scope_mems:
            similar = m.search(mem.get("memory", ""), user_id="default", filters={"scope": scope}, limit=5)
            items = similar if isinstance(similar, list) else similar.get("results", [])
            for item in items:
                if item.get("id") == mem.get("id"):
                    continue
                score = item.get("score", 0)
                pair = tuple(sorted([mem.get("id", ""), item.get("id", "")]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if score >= auto_threshold:
                    older_id = mem.get("id") if (mem.get("created_at", "") < item.get("created_at", "")) else item.get("id")
                    newer_id = item.get("id") if older_id == mem.get("id") else mem.get("id")
                    try:
                        qc.set_payload(collection, payload={"archived": True, "superseded_by": newer_id}, points=[older_id])
                        auto_merged += 1
                    except Exception:
                        pass

    report["dedup_auto_merged"] = auto_merged


def step_decay(memories, qc, report):
    """Apply decay and archive low-importance memories."""
    from engines.decay import compute_importance
    collection = CFG["qdrant"]["collection"]
    decay_cfg = CFG.get("decay", {})
    threshold = decay_cfg.get("archive_threshold", 0.10)
    archived = 0

    for mem in memories:
        if mem.get("metadata", {}).get("archived"):
            continue
        imp = compute_importance(mem, config=decay_cfg)
        if imp < threshold:
            mid = mem.get("id", "")
            if mid:
                try:
                    qc.set_payload(collection, payload={"archived": True}, points=[mid])
                    archived += 1
                except Exception:
                    pass

    report["decay_archived"] = archived


def step_consolidation(m, qc, memories, llm_call, report):
    """Consolidate fragmented task_logs into knowledge summaries."""
    from engines.consolidation import find_consolidation_groups, consolidate_group, mark_consolidated_sources
    collection = CFG["qdrant"]["collection"]
    consolidated = 0

    scopes = set(mem.get("metadata", {}).get("scope", "global") for mem in memories)
    for scope in scopes:
        scope_mems = [m2 for m2 in memories if m2.get("metadata", {}).get("scope") == scope]
        groups = find_consolidation_groups(scope_mems)
        for group in groups:
            result = consolidate_group(group, llm_call, scope)
            if result:
                try:
                    new_mem = m.add(result["content"], user_id="default", metadata={
                        "scope": scope, "mem_type": "knowledge", "source": "consolidation",
                        "trust": "medium", "agent": "maintenance",
                        "consolidated_from": json.dumps(result.get("consolidated_from", [])),
                        "access_count": 0, "archived": False,
                        "embedding_model": CFG["embedding"]["primary"]["model"],
                        "schema_version": CFG["schema_version"],
                    })
                    new_id = ""
                    if isinstance(new_mem, dict):
                        results = new_mem.get("results", [])
                        if results:
                            new_id = results[0].get("id", "")
                    if new_id:
                        mark_consolidated_sources(result.get("consolidated_from", []), new_id, qc, collection)
                    consolidated += 1
                except Exception:
                    pass

    report["consolidated_groups"] = consolidated


def step_conflict(m, qc, memories, llm_call, report):
    """Detect and resolve conflicting memories."""
    from engines.conflict import detect_conflicts, resolve_conflict, apply_resolution
    collection = CFG["qdrant"]["collection"]
    resolved = 0

    scopes = set(mem.get("metadata", {}).get("scope", "global") for mem in memories)
    for scope in scopes:
        scope_mems = [m2 for m2 in memories if m2.get("metadata", {}).get("scope") == scope]
        pairs = detect_conflicts(scope_mems)
        for a, b in pairs[:10]:
            resolution = resolve_conflict(a, b, llm_call)
            if resolution.get("conflicts"):
                apply_resolution(resolution, a, b, qc, collection)
                resolved += 1

    report["conflicts_resolved"] = resolved


def generate_report(m, report, qc=None):
    """Generate final statistics."""
    all_mems = get_all_memories(m, qc=qc)
    active = [mem for mem in all_mems if not mem.get("metadata", {}).get("archived")]
    archived = len(all_mems) - len(active)

    by_scope, by_type = {}, {}
    for mem in active:
        meta = mem.get("metadata", {})
        s = meta.get("scope", "unknown")
        t = meta.get("mem_type", "unknown")
        by_scope[s] = by_scope.get(s, 0) + 1
        by_type[t] = by_type.get(t, 0) + 1

    report.update({
        "total_memories": len(all_mems),
        "active_memories": len(active),
        "archived_memories": archived,
        "by_scope": by_scope,
        "by_type": by_type,
        "unscoped_active": by_scope.get("unscoped", 0),
    })
    if qc is not None:
        report["inventory_source"] = "qdrant_scroll"
    return report


def send_feishu_report(report):
    """Send report summary to Feishu."""
    mode = report.get("mode", "unknown")
    msg = f"[记忆维护报告] {report.get('date', '')} ({mode})\n"
    msg += f"耗时: {report.get('elapsed_seconds', 0):.0f}s\n\n"

    if "re_extract_ok" in report:
        msg += f"Opus重提取: {report['re_extract_ok']}/{report.get('re_extract_total', 0)}\n"
    if "dedup_auto_merged" in report:
        msg += f"自动去重: {report['dedup_auto_merged']} 对合并\n"
    if "conflicts_resolved" in report:
        msg += f"冲突解决: {report['conflicts_resolved']}\n"
    if "consolidated_groups" in report:
        msg += f"巩固: {report['consolidated_groups']} 组\n"
    if "decay_archived" in report:
        msg += f"衰减归档: {report['decay_archived']}\n"

    msg += f"\n总量: {report.get('total_memories', 0)} (active {report.get('active_memories', 0)}, archived {report.get('archived_memories', 0)})\n"
    msg += f"scope: {json.dumps(report.get('by_scope', {}), ensure_ascii=False)}\n"
    msg += f"type: {json.dumps(report.get('by_type', {}), ensure_ascii=False)}\n"

    if report.get("errors"):
        msg += f"\n错误: {len(report['errors'])} 条\n"

    try:
        env = {**os.environ, "PATH": "/usr/local/bin:" + os.environ.get("PATH", "")}
        subprocess.run(["echo", "--text", msg[:2000]], timeout=15, capture_output=True, env=env)
    except Exception:
        pass

    return msg


def run(mode="daily"):
    t0 = time.time()
    report = {"mode": mode, "date": datetime.now().strftime("%Y-%m-%d %H:%M")}

    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    _load_env_layers()
    oc = json.load(open(HOST_CONFIG_PATH))
    qc = QdrantClient(host=CFG["qdrant"]["host"], port=CFG["qdrant"]["port"])

    if mode == "report_only":
        lingyun_provider = _resolved_provider(oc, "lingyun-gemini")
        m_daily = _make_memory_with_embedder_fallback(oc, {
            "provider": "openai",
            "config": {
                "model": "gemini-2.5-flash",
                "api_key": lingyun_provider.get("apiKey") or os.environ.get("LINGYUN_GEMINI_API_KEY"),
                "openai_base_url": _normalize_openai_base_url(
                    lingyun_provider.get("baseUrl"),
                    "https://your-proxy.example.com/v1",
                ),
            },
        })
        memories = get_all_memories(m_daily, qc=qc)
        report = generate_report(m_daily, report, qc=qc)
        report["elapsed_seconds"] = time.time() - t0
        msg = send_feishu_report(report)
        print(msg)
        return report

    opus_mem = _make_opus_memory()
    llm_call = _make_llm_call(oc)
    memories = get_all_memories(opus_mem, qc=qc)

    plan = {
        "date": report["date"],
        "mode": mode,
        "total_memories": len(memories),
        "today_new": len(get_today_memories(memories)),
    }
    plan_path = PLAN_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M')}_{mode}.json"
    with open(plan_path, "w") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # Daily steps (always run)
    print("Step 1: Opus re-extract...")
    step_opus_reextract(opus_mem, memories, report)

    memories = get_all_memories(opus_mem, qc=qc)

    print("Step 2-3: Dedup...")
    step_dedup(opus_mem, qc, memories, report)

    # Weekly steps (only on weekly mode)
    if mode == "weekly":
        print("Step 4: Conflict detection...")
        step_conflict(opus_mem, qc, memories, llm_call, report)

        print("Step 5: Consolidation...")
        step_consolidation(opus_mem, qc, memories, llm_call, report)

        print("Step 6: Decay...")
        step_decay(memories, qc, report)

    memories = get_all_memories(opus_mem, qc=qc)
    report = generate_report(opus_mem, report, qc=qc)
    report["elapsed_seconds"] = time.time() - t0

    report_path = REPORT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M')}_{mode}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    msg = send_feishu_report(report)
    print(msg)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="daily", choices=["daily", "weekly", "report_only"])
    args = parser.parse_args()
    run(args.mode)
