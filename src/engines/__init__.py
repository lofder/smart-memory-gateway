"""Cognitive engines for Smart Memory Gateway v3."""
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
