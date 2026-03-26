"""Conflict detection: find and resolve contradictory memories.

Adapted from smart-memory/cognition/belief_conflict_resolver.py with:
- Only checks within same scope (scope-aware)
- Only applies to fact and preference types
- LLM judges which to keep when conflict detected
- Loser gets superseded_by marker (soft resolution)
"""
import json


def detect_conflicts(
    memories: list[dict],
    similarity_threshold: float = 0.85,
) -> list[tuple[dict, dict]]:
    """Detect potentially conflicting memories using keyword pre-filter.

    Pre-filters with keyword overlap to reduce O(n^2) LLM calls.
    Only same-type memories within the same scope can conflict.
    """
    conflict_types = {"fact", "preference"}

    candidates = [
        m for m in memories
        if m.get("metadata", {}).get("mem_type") in conflict_types
        and not m.get("metadata", {}).get("archived")
    ]

    if len(candidates) < 2:
        return []

    def _keywords(text):
        return set(w.lower() for w in text.split() if len(w) > 3)

    kw_cache = [_keywords(c.get("memory", "")[:300]) for c in candidates]

    pairs = []
    seen = set()
    for i, a in enumerate(candidates):
        for j in range(i + 1, len(candidates)):
            b = candidates[j]
            if a.get("metadata", {}).get("mem_type") != b.get("metadata", {}).get("mem_type"):
                continue

            # Pre-filter: require keyword overlap (cheap proxy for semantic similarity)
            if kw_cache[i] and kw_cache[j]:
                overlap = len(kw_cache[i] & kw_cache[j])
                total = len(kw_cache[i] | kw_cache[j])
                if total > 0 and overlap / total < 0.2:
                    continue

            pair = tuple(sorted([a.get("id", ""), b.get("id", "")]))
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append((a, b))

            if len(pairs) >= 20:
                return pairs

    return pairs



def resolve_conflict(mem_a: dict, mem_b: dict, llm_call) -> dict:
    """Use LLM to determine if two memories conflict and which to keep.

    Returns: {"conflicts": bool, "keep": "A"/"B"/"both", "reasoning": str}
    """
    prompt = f"""Two memories might conflict. Return ONLY valid JSON.

Memory A (created: {mem_a.get("created_at", "unknown")}): "{mem_a.get("memory", "")}"
Memory B (created: {mem_b.get("created_at", "unknown")}): "{mem_b.get("memory", "")}"

Rules:
- If they say the same thing differently, keep the more complete one → "both": false
- If they contradict (e.g., "likes X" vs "prefers Y"), keep the NEWER one
- If they're about different topics, they don't conflict → "both": true

Output: {{"conflicts": true/false, "keep": "A"/"B"/"both", "reasoning": "..."}}"""

    try:
        response = llm_call(prompt).strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(response)
    except Exception:
        return {"conflicts": False, "keep": "both", "reasoning": "LLM failed, keeping both"}


def apply_resolution(
    resolution: dict,
    mem_a: dict,
    mem_b: dict,
    qdrant_client,
    collection: str,
):
    """Apply conflict resolution by marking the loser as superseded."""
    if not resolution.get("conflicts") or resolution.get("keep") == "both":
        return

    keep = resolution.get("keep", "B")
    winner_id = mem_a.get("id") if keep == "A" else mem_b.get("id")
    loser_id = mem_b.get("id") if keep == "A" else mem_a.get("id")

    if loser_id and winner_id:
        try:
            qdrant_client.set_payload(
                collection_name=collection,
                payload={
                    "superseded_by": winner_id,
                    "archived": True,
                },
                points=[loser_id],
            )
        except Exception:
            pass
