from __future__ import annotations
"""Decay engine — importance scoring based on age, access frequency, and memory type.
衰减引擎 — 基于年龄、访问频率和记忆类型的重要性评分。

Formula / 公式:
  I(t) = importance × exp(-λ × age_days / divisor)
  divisor = 1 + min(log(1 + access_count), cap)
  λ = ln(2) / half_life_days

Per-type half-life / 按类型差异化半衰期:
  - task_log: 30 days / 30 天（日志衰减快）
  - procedure: 90 days / 90 天（操作手册衰减慢）
  - fact/preference/lesson/decision/knowledge: never / 永不衰减

Bjork storage-retrieval strength theory (1992):
  Memories accessed more frequently decay slower.
  被频繁检索的记忆衰减更慢（间隔效应）。
  access_count >= 20 → protection effect capped / 保护效果封顶。
"""
import math
from datetime import datetime, timezone


def compute_importance(
    memory: dict,
    now: datetime | None = None,
    config: dict | None = None,
) -> float:
    """Compute current importance score for a memory.
    计算一条记忆的当前重要性分数。

    Returns float 0.0-1.0. Lower = more decayed = candidate for archival.
    返回 0.0-1.0 的浮点数。越低 = 衰减越多 = 归档候选。
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
    """Return IDs of memories whose importance has decayed below threshold.
    返回重要性低于阈值的记忆 ID 列表（归档候选）。
    """
    now = datetime.now(timezone.utc)
    candidates = []
    for mem in memories:
        imp = compute_importance(mem, now=now, config=config)
        if imp < threshold:
            mid = mem.get("id", "")
            if mid:
                candidates.append(mid)
    return candidates
