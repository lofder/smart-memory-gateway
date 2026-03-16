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
) -> list[list[dict]]:
    """Group memories by shared entities/topics for consolidation.

    Simple heuristic: group by first entity or by similar content keywords.
    """
    groups: dict[str, list[dict]] = {}

    for mem in memories:
        meta = mem.get("metadata", {})
        if meta.get("mem_type") != "task_log":
            continue
        if meta.get("archived"):
            continue

        content = mem.get("memory", "")
        key_words = set(content[:50].split())
        group_key = "_".join(sorted(list(key_words)[:3])) if key_words else "_ungrouped"

        groups.setdefault(group_key, []).append(mem)

    return [g for g in groups.values() if len(g) >= min_group_size]


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
    """Mark original memories as consolidated (accelerated decay, not deleted)."""
    for sid in source_ids:
        try:
            qdrant_client.set_payload(
                collection_name=collection,
                payload={"consolidated_into": new_memory_id},
                points=[sid],
            )
        except Exception:
            pass
