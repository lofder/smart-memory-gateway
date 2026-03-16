"""Cognitive engines for Smart Memory Gateway v3.
智能记忆网关 v3 的认知引擎模块。

Engines / 引擎:
  - decay:         Importance scoring with Bjork-enhanced exponential decay / 基于 Bjork 理论的重要性衰减
  - classifier:    Two-layer cascade classifier (keywords + LLM) / 两层级联分类器（关键词 + LLM）
  - consolidation: Merge fragmented memories into knowledge summaries / 将碎片记忆合并为知识摘要
  - conflict:      Detect and resolve contradictory memories / 检测并解决矛盾记忆
"""
from .decay import compute_importance, find_archive_candidates
from .classifier import classify, classify_by_keywords, classify_by_llm
from .consolidation import find_consolidation_groups, consolidate_group, mark_consolidated_sources
from .conflict import detect_conflicts, resolve_conflict, apply_resolution

__all__ = [
    "compute_importance", "find_archive_candidates",
    "classify", "classify_by_keywords", "classify_by_llm",
    "find_consolidation_groups", "consolidate_group", "mark_consolidated_sources",
    "detect_conflicts", "resolve_conflict", "apply_resolution",
]
