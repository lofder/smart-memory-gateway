from __future__ import annotations
"""Decay engine: importance scoring based on age, access frequency, and memory type.

Adapted from smart-memory/cognition/decay_agent.py with optimizations:
- Per-type half-life (task_log=30d, procedure=90d, fact/preference/lesson/decision=never)
- Bjork storage-retrieval strength: access_count extends effective half-life
- Access count cap: min(log(1+N), 3.0) to prevent immortal memories
"""
import math
from datetime import datetime, timezone


def compute_importance(
    memory: dict,
    now: datetime | None = None,
    config: dict | None = None,
) -> float:
    """Compute current importance score for a memory.

    Returns float 0.0-1.0. Lower = more decayed = candidate for archival.
    """
    now = now or datetime.now(timezone.utc)
    cfg = config or {}

    meta = memory.get("metadata", {})
    mem_type = meta.get("mem_type", "")

    half_lives = {
        "task_log": cfg.get("task_log_half_life_days", 30),
        "procedure": cfg.get("procedure_half_life_days", 90),
    }
    never_decay = {"fact", "preference", "lesson", "decision", "knowledge"}

    if mem_type in never_decay:
        return 1.0

    half_life = half_lives.get(mem_type, 60)

    created_str = memory.get("created_at") or meta.get("created_at", "")
    if not created_str:
        return 1.0

    try:
        if isinstance(created_str, datetime):
            created = created_str
        else:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return 1.0

    age_days = max(0.0, (now - created).total_seconds() / 86400.0)

    access_count = meta.get("access_count", 0)
    cap = cfg.get("access_count_cap", 3.0)
    divisor = 1.0 + min(math.log(1.0 + access_count), cap)

    effective_age = age_days / divisor

    decay_lambda = math.log(2.0) / max(1.0, half_life)
    importance = math.exp(-decay_lambda * effective_age)

    return max(0.0, min(1.0, importance))


def find_archive_candidates(
    memories: list[dict],
    threshold: float = 0.10,
    config: dict | None = None,
) -> list[str]:
    """Return IDs of memories whose importance has decayed below threshold."""
    now = datetime.now(timezone.utc)
    candidates = []
    for mem in memories:
        imp = compute_importance(mem, now=now, config=config)
        if imp < threshold:
            mid = mem.get("id", "")
            if mid:
                candidates.append(mid)
    return candidates
