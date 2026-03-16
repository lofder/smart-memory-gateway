"""Unit tests for cognitive engines.
认知引擎单元测试。

Run: python -m pytest tests/test_engines.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from engines.decay import compute_importance, find_archive_candidates
from engines.classifier import classify_by_keywords, classify
from engines.conflict import detect_conflicts


class TestDecay:
    """Decay engine tests / 衰减引擎测试"""

    def test_task_log_decays(self):
        """40-day task_log should decay to ~0.4 (half-life 30d)"""
        mem = {"metadata": {"mem_type": "task_log", "access_count": 0},
               "created_at": "2026-02-01T00:00:00+00:00"}
        imp = compute_importance(mem)
        assert 0.3 < imp < 0.5, f"Expected ~0.4, got {imp}"

    def test_preference_never_decays(self):
        """Preferences should never decay / 偏好永不衰减"""
        mem = {"metadata": {"mem_type": "preference"},
               "created_at": "2025-01-01T00:00:00+00:00"}
        assert compute_importance(mem) == 1.0

    def test_fact_never_decays(self):
        """Facts should never decay / 事实永不衰减"""
        mem = {"metadata": {"mem_type": "fact"},
               "created_at": "2024-06-01T00:00:00+00:00"}
        assert compute_importance(mem) == 1.0

    def test_access_count_slows_decay(self):
        """Higher access_count should slow decay / 高访问次数减缓衰减"""
        base = {"metadata": {"mem_type": "task_log", "access_count": 0},
                "created_at": "2026-02-01T00:00:00+00:00"}
        frequent = {"metadata": {"mem_type": "task_log", "access_count": 50},
                    "created_at": "2026-02-01T00:00:00+00:00"}
        assert compute_importance(frequent) > compute_importance(base)

    def test_access_count_cap(self):
        """access_count effect should be capped / 访问次数效果有上限"""
        mem_100 = {"metadata": {"mem_type": "task_log", "access_count": 100},
                   "created_at": "2026-02-01T00:00:00+00:00"}
        mem_10000 = {"metadata": {"mem_type": "task_log", "access_count": 10000},
                     "created_at": "2026-02-01T00:00:00+00:00"}
        diff = abs(compute_importance(mem_10000) - compute_importance(mem_100))
        assert diff < 0.01, f"Cap not working, diff={diff}"

    def test_archive_candidates(self):
        """Very old task_logs should be archive candidates / 很旧的 task_log 应该被归档"""
        old = {"id": "old1", "metadata": {"mem_type": "task_log", "access_count": 0},
               "created_at": "2025-01-01T00:00:00+00:00"}
        new = {"id": "new1", "metadata": {"mem_type": "task_log", "access_count": 0},
               "created_at": "2026-03-13T00:00:00+00:00"}
        candidates = find_archive_candidates([old, new])
        assert "old1" in candidates
        assert "new1" not in candidates


class TestClassifier:
    """Classifier tests / 分类器测试"""

    def test_preference_keywords(self):
        """Keywords like '以后' should classify as preference / '以后' 应分类为偏好"""
        assert classify_by_keywords("以后文案都用简约风格") == "preference"

    def test_procedure_keywords(self):
        """Operation commands classify as procedure / 操作命令分类为 procedure"""
        assert classify_by_keywords("Gateway 重启命令是 launchctl") == "procedure"

    def test_transient_keywords(self):
        """Simple confirmations are transient / 简单确认是 transient"""
        assert classify_by_keywords("好的") == "transient"
        assert classify_by_keywords("OK") == "transient"

    def test_lesson_keywords(self):
        """Lessons learned classify as lesson / 教训分类为 lesson"""
        assert classify_by_keywords("上次搞错了因为...") == "lesson"

    def test_ambiguous_returns_none(self):
        """Ambiguous content returns None (needs LLM) / 歧义内容返回 None"""
        assert classify_by_keywords("磁扣充电宝销量不错") is None

    def test_classify_fallback_to_task_log(self):
        """Without LLM, ambiguous defaults to task_log / 无 LLM 时歧义默认 task_log"""
        assert classify("磁扣充电宝销量不错") == "task_log"


class TestConflict:
    """Conflict detection tests / 冲突检测测试"""

    def test_same_type_detected(self):
        """Same mem_type pairs should be candidates / 相同类型应被检测"""
        mems = [
            {"id": "a", "metadata": {"mem_type": "preference", "archived": False}},
            {"id": "b", "metadata": {"mem_type": "preference", "archived": False}},
        ]
        pairs = detect_conflicts(mems)
        assert len(pairs) == 1

    def test_different_types_ignored(self):
        """Different types should not be conflict candidates / 不同类型不应被检测"""
        mems = [
            {"id": "a", "metadata": {"mem_type": "preference", "archived": False}},
            {"id": "b", "metadata": {"mem_type": "procedure", "archived": False}},
        ]
        pairs = detect_conflicts(mems)
        assert len(pairs) == 0

    def test_archived_excluded(self):
        """Archived memories should be excluded / 已归档记忆应被排除"""
        mems = [
            {"id": "a", "metadata": {"mem_type": "preference", "archived": True}},
            {"id": "b", "metadata": {"mem_type": "preference", "archived": False}},
        ]
        pairs = detect_conflicts(mems)
        assert len(pairs) == 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
