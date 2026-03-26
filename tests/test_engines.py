"""Unit tests for cognitive engines.

Run: python -m pytest tests/test_engines.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from engines.decay import compute_importance, find_archive_candidates
from engines.classifier import classify_by_keywords, classify
from engines.conflict import detect_conflicts
from engines.consolidation import find_consolidation_groups


class TestDecay:
    """Decay engine tests"""

    def test_task_log_decays(self):
        """task_log with fixed age should decay predictably"""
        from datetime import datetime, timezone
        now = datetime(2026, 3, 13, tzinfo=timezone.utc)
        mem = {"metadata": {"mem_type": "task_log", "access_count": 0},
               "created_at": "2026-02-01T00:00:00+00:00"}
        imp = compute_importance(mem, now=now)
        assert 0.3 < imp < 0.5, f"Expected ~0.4, got {imp}"

    def test_preference_never_decays(self):
        mem = {"metadata": {"mem_type": "preference"},
               "created_at": "2025-01-01T00:00:00+00:00"}
        assert compute_importance(mem) == 1.0

    def test_fact_never_decays(self):
        mem = {"metadata": {"mem_type": "fact"},
               "created_at": "2024-06-01T00:00:00+00:00"}
        assert compute_importance(mem) == 1.0

    def test_knowledge_never_decays(self):
        mem = {"metadata": {"mem_type": "knowledge"},
               "created_at": "2024-01-01T00:00:00+00:00"}
        assert compute_importance(mem) == 1.0

    def test_decision_never_decays(self):
        mem = {"metadata": {"mem_type": "decision"},
               "created_at": "2024-01-01T00:00:00+00:00"}
        assert compute_importance(mem) == 1.0

    def test_access_count_slows_decay(self):
        base = {"metadata": {"mem_type": "task_log", "access_count": 0},
                "created_at": "2026-02-01T00:00:00+00:00"}
        frequent = {"metadata": {"mem_type": "task_log", "access_count": 50},
                    "created_at": "2026-02-01T00:00:00+00:00"}
        assert compute_importance(frequent) > compute_importance(base)

    def test_access_count_cap(self):
        mem_100 = {"metadata": {"mem_type": "task_log", "access_count": 100},
                   "created_at": "2026-02-01T00:00:00+00:00"}
        mem_10000 = {"metadata": {"mem_type": "task_log", "access_count": 10000},
                     "created_at": "2026-02-01T00:00:00+00:00"}
        diff = abs(compute_importance(mem_10000) - compute_importance(mem_100))
        assert diff < 0.01, f"Cap not working, diff={diff}"

    def test_archive_candidates(self):
        old = {"id": "old1", "metadata": {"mem_type": "task_log", "access_count": 0},
               "created_at": "2025-01-01T00:00:00+00:00"}
        new = {"id": "new1", "metadata": {"mem_type": "task_log", "access_count": 0},
               "created_at": "2026-03-13T00:00:00+00:00"}
        candidates = find_archive_candidates([old, new])
        assert "old1" in candidates
        assert "new1" not in candidates

    def test_procedure_decays_slower_than_task_log(self):
        from datetime import datetime, timezone
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        task = {"metadata": {"mem_type": "task_log", "access_count": 0},
                "created_at": "2026-03-01T00:00:00+00:00"}
        proc = {"metadata": {"mem_type": "procedure", "access_count": 0},
                "created_at": "2026-03-01T00:00:00+00:00"}
        assert compute_importance(proc, now=now) > compute_importance(task, now=now)

    def test_missing_created_at_returns_one(self):
        mem = {"metadata": {"mem_type": "task_log", "access_count": 0}}
        assert compute_importance(mem) == 1.0


class TestClassifier:
    """Classifier tests"""

    def test_preference_keywords_cn(self):
        assert classify_by_keywords("以后文案都用简约风格") == "preference"

    def test_preference_keywords_en(self):
        assert classify_by_keywords("I always prefer dark mode") == "preference"

    def test_procedure_keywords(self):
        assert classify_by_keywords("Gateway 重启命令是 launchctl") == "procedure"

    def test_transient_keywords(self):
        assert classify_by_keywords("好的") == "transient"
        assert classify_by_keywords("OK") == "transient"

    def test_lesson_keywords(self):
        assert classify_by_keywords("上次搞错了因为...") == "lesson"

    def test_decision_keywords(self):
        assert classify_by_keywords("最终方案确定了") == "decision"

    def test_fact_keywords(self):
        assert classify_by_keywords("我叫小明") == "fact"

    def test_ambiguous_returns_none(self):
        assert classify_by_keywords("磁扣充电宝销量不错") is None

    def test_classify_fallback_to_task_log(self):
        assert classify("磁扣充电宝销量不错") == "task_log"


class TestConflict:
    """Conflict detection tests"""

    def test_same_type_detected(self):
        mems = [
            {"id": "a", "memory": "user prefers dark mode theme always",
             "metadata": {"mem_type": "preference", "archived": False}},
            {"id": "b", "memory": "user prefers dark mode for editor",
             "metadata": {"mem_type": "preference", "archived": False}},
        ]
        pairs = detect_conflicts(mems)
        assert len(pairs) == 1

    def test_different_types_ignored(self):
        mems = [
            {"id": "a", "memory": "something about preferences",
             "metadata": {"mem_type": "preference", "archived": False}},
            {"id": "b", "memory": "something about procedures",
             "metadata": {"mem_type": "procedure", "archived": False}},
        ]
        pairs = detect_conflicts(mems)
        assert len(pairs) == 0

    def test_archived_excluded(self):
        mems = [
            {"id": "a", "memory": "user prefers dark mode",
             "metadata": {"mem_type": "preference", "archived": True}},
            {"id": "b", "memory": "user prefers dark mode too",
             "metadata": {"mem_type": "preference", "archived": False}},
        ]
        pairs = detect_conflicts(mems)
        assert len(pairs) == 0

    def test_keyword_prefilter_skips_unrelated(self):
        """Completely unrelated content should be filtered by keyword overlap"""
        mems = [
            {"id": "a", "memory": "deploy kubernetes production cluster upgrade",
             "metadata": {"mem_type": "fact", "archived": False}},
            {"id": "b", "memory": "chocolate cake recipe ingredients baking",
             "metadata": {"mem_type": "fact", "archived": False}},
        ]
        pairs = detect_conflicts(mems)
        assert len(pairs) == 0

    def test_max_pairs_limit(self):
        """Should cap at 20 pairs even with many candidates"""
        mems = []
        for i in range(50):
            mems.append({
                "id": f"m{i}",
                "memory": f"user setting config option number {i} preference value",
                "metadata": {"mem_type": "preference", "archived": False},
            })
        pairs = detect_conflicts(mems)
        assert len(pairs) <= 20

    def test_single_memory_returns_empty(self):
        mems = [{"id": "a", "memory": "solo",
                 "metadata": {"mem_type": "fact", "archived": False}}]
        assert detect_conflicts(mems) == []


class TestConsolidation:
    """Consolidation grouping tests"""

    def test_similar_content_groups_together(self):
        mems = [
            {"id": "1", "memory": "deployed backend service version 2.1 today",
             "metadata": {"mem_type": "task_log", "archived": False}},
            {"id": "2", "memory": "deployed backend service version 2.2 update",
             "metadata": {"mem_type": "task_log", "archived": False}},
            {"id": "3", "memory": "deployed backend service version 2.3 patch",
             "metadata": {"mem_type": "task_log", "archived": False}},
        ]
        groups = find_consolidation_groups(mems)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_non_task_log_excluded(self):
        mems = [
            {"id": "1", "memory": "user likes dark mode",
             "metadata": {"mem_type": "preference", "archived": False}},
            {"id": "2", "memory": "user likes dark theme",
             "metadata": {"mem_type": "preference", "archived": False}},
            {"id": "3", "memory": "user likes dark colors",
             "metadata": {"mem_type": "preference", "archived": False}},
        ]
        groups = find_consolidation_groups(mems)
        assert len(groups) == 0

    def test_archived_excluded(self):
        mems = [
            {"id": "1", "memory": "deployed backend service v1",
             "metadata": {"mem_type": "task_log", "archived": True}},
            {"id": "2", "memory": "deployed backend service v2",
             "metadata": {"mem_type": "task_log", "archived": False}},
            {"id": "3", "memory": "deployed backend service v3",
             "metadata": {"mem_type": "task_log", "archived": False}},
        ]
        groups = find_consolidation_groups(mems)
        for g in groups:
            assert all(not m["metadata"]["archived"] for m in g)

    def test_min_group_size_respected(self):
        mems = [
            {"id": "1", "memory": "same content repeated here",
             "metadata": {"mem_type": "task_log", "archived": False}},
            {"id": "2", "memory": "same content repeated there",
             "metadata": {"mem_type": "task_log", "archived": False}},
        ]
        groups = find_consolidation_groups(mems, min_group_size=3)
        assert len(groups) == 0

    def test_max_groups_limit(self):
        mems = []
        for i in range(100):
            mems.append({
                "id": f"m{i}",
                "memory": f"unique topic {i} with distinct keywords for group {i}",
                "metadata": {"mem_type": "task_log", "archived": False},
            })
        groups = find_consolidation_groups(mems, min_group_size=1, max_groups=10)
        assert len(groups) <= 10

    def test_dissimilar_content_not_grouped(self):
        mems = [
            {"id": "1", "memory": "kubernetes cluster deployment upgrade production",
             "metadata": {"mem_type": "task_log", "archived": False}},
            {"id": "2", "memory": "chocolate recipe ingredients baking oven temperature",
             "metadata": {"mem_type": "task_log", "archived": False}},
            {"id": "3", "memory": "quantum physics electron wave particle duality",
             "metadata": {"mem_type": "task_log", "archived": False}},
        ]
        groups = find_consolidation_groups(mems)
        assert len(groups) == 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
