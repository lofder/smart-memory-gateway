from __future__ import annotations
"""Consolidation engine: merge related memories into knowledge summaries.

Adapted from smart-memory/cognition/memory_consolidation_agent.py with:
- LLM-based semantic summary (not simple text concatenation)
- consolidated_from tracking for provenance
- Original memories get accelerated decay, not hard-deleted
- Scope-aware: only consolidates within the same scope
"""
import json


def find_consolidation_groups(
    memories: list[dict],
    similarity_threshold: float = 0.80,
    min_group_size: int = 3,
    max_groups: int = 10,
) -> list[list[dict]]:
    """Group task_log memories by content similarity using keyword overlap.

    Uses a Union-Find approach with keyword-based similarity as a proxy
    for semantic similarity. Limited to max_groups to bound LLM calls.
    """
    candidates = []
    for mem in memories:
        meta = mem.get("metadata", {})
        if meta.get("mem_type") != "task_log":
            continue
        if meta.get("archived"):
            continue
        candidates.append(mem)

    if not candidates:
        return []

    # Union-Find for grouping
    parent = list(range(len(candidates)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Group by keyword overlap (cheap proxy for semantic similarity)
    def _keywords(text):
        return set(w.lower() for w in text.split() if len(w) > 3)

    kw_cache = [_keywords(c.get("memory", "")[:200]) for c in candidates]

    for i in range(len(candidates)):
        for j in range(i + 1, min(i + 50, len(candidates))):
            if not kw_cache[i] or not kw_cache[j]:
                continue
            overlap = len(kw_cache[i] & kw_cache[j])
            total = len(kw_cache[i] | kw_cache[j])
            if total > 0 and overlap / total >= 0.3:
                union(i, j)

    # Collect groups
    groups_map: dict[int, list[dict]] = {}
    for i, mem in enumerate(candidates):
        root = find(i)
        groups_map.setdefault(root, []).append(mem)

    result = [g for g in groups_map.values() if len(g) >= min_group_size]
    result.sort(key=len, reverse=True)
    return result[:max_groups]


def consolidate_group(memories: list[dict], llm_call, scope: str) -> dict | None:
    """Consolidate a group of memories into a single knowledge summary.

    Args:
        memories: List of related memories to consolidate
        llm_call: callable(prompt) -> str, LLM for summarization
        scope: The scope these memories belong to

    Returns:
        New memory dict ready for mem0_add, or None on failure
    """
    if not memories or not llm_call:
        return None

    contents = "\n".join(f"- {m.get('memory', '')[:200]}" for m in memories[:10])
    source_ids = [m.get("id", "") for m in memories if m.get("id")]

    prompt = f"""Summarize these related memories into ONE concise knowledge statement.
Keep all key facts, decisions, and lessons. Remove redundancy.
Output ONLY the summary text, no JSON, no markdown.

Memories:
{contents}"""

    try:
        summary = llm_call(prompt).strip()
        if not summary or len(summary) < 10:
            return None

        return {
            "content": summary,
            "scope": scope,
            "mem_type": "knowledge",
            "source": "consolidation",
            "trust": "medium",
            "consolidated_from": source_ids,
        }
    except Exception:
        return None


def mark_consolidated_sources(source_ids: list[str], new_memory_id: str, qdrant_client, collection: str):
    """Mark original memories as consolidated and archived."""
    # Verify the new knowledge memory actually exists before archiving sources
    try:
        verify = qdrant_client.retrieve(collection_name=collection, ids=[new_memory_id], with_payload=True)
        if not verify:
            import sys
            sys.stderr.write(f"consolidation: cannot archive sources — new memory {new_memory_id} not found\n")
            return
    except Exception:
        return

    for sid in source_ids:
        try:
            qdrant_client.set_payload(
                collection_name=collection,
                payload={"consolidated_into": new_memory_id, "archived": True},
                points=[sid],
            )
        except Exception:
            pass
