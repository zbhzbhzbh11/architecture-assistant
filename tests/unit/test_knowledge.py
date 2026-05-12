"""知识库模块单元测试."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.knowledge_base.app.main import load_styles, add_style, add_feedback, get_feedback_stats, StylePayload, FeedbackPayload


class TestKnowledgeBaseLoad:
    """知识库加载与数据完整性测试."""

    def test_styles_count_at_least_10(self):
        """检查架构风格数量 >= 10."""
        data = load_styles()
        styles = data["styles"]
        assert len(styles) >= 10, f"架构风格数量不足: {len(styles)} < 10"

    def test_each_style_has_required_fields(self):
        """检查每种架构风格包含必填字段: name, tags, best_for, pros, cons."""
        data = load_styles()
        required = {"name", "tags", "best_for", "pros", "cons"}
        for style in data["styles"]:
            missing = required - set(style.keys())
            name = style.get("name", "?")
            assert not missing, f"{name}: 缺少字段 {missing}"

    def test_contains_mainstream_styles(self):
        """检查是否包含分层架构、微服务架构、事件驱动架构."""
        data = load_styles()
        names = {s["name"] for s in data["styles"]}
        mainstream = [
            "Layered Architecture",
            "Microservices",
            "Event-Driven Architecture",
        ]
        missing = [m for m in mainstream if m not in names]
        assert not missing, f"缺少主流架构: {missing}"

    def test_topo_mermaid_not_empty(self):
        """检查每种风格都有拓扑图定义."""
        data = load_styles()
        for style in data["styles"]:
            topo = style.get("topology_mermaid", "")
            name = style.get("name", "?")
            assert topo, f"{name}: 缺少 topology_mermaid"

    def test_pros_cons_non_empty(self):
        """检查每种风格的优缺点非空."""
        data = load_styles()
        for style in data["styles"]:
            name = style.get("name", "?")
            assert len(style.get("pros", [])) > 0, f"{name}: pros 为空"
            assert len(style.get("cons", [])) > 0, f"{name}: cons 为空"


class TestKnowledgeExtension:
    """知识库扩展接口测试."""

    def test_add_style(self):
        """POST /styles 新增风格后总数 +1."""
        before = load_styles()
        count_before = len(before["styles"])

        payload = StylePayload(
            name="Test Style",
            tags=["scalability"],
            best_for=["testing"],
            pros=["easy to test"],
            cons=["not real"],
        )
        result = add_style(payload)
        assert result["status"] == "ok"

        after = load_styles()
        count_after = len(after["styles"])
        assert count_after == count_before + 1

        # 清理：手动从文件中移除测试风格
        after["styles"] = [s for s in after["styles"] if s["name"] != "Test Style"]
        from services.knowledge_base.app.main import save_styles
        save_styles(after)


class TestFeedback:
    """案例学习反馈接口测试."""

    def test_add_and_stats(self):
        """添加一条反馈后 stats 应更新."""
        payload = FeedbackPayload(
            requirement="测试需求",
            recommended_style="Layered Architecture",
            user_choice="Microservices",
            comment="测试反馈",
        )
        result = add_feedback(payload)
        assert result["status"] == "ok"

        stats = get_feedback_stats()
        assert stats["total"] >= 1
        # 清理：删除刚添加的测试反馈
        from services.knowledge_base.app.main import FEEDBACK_PATH
        import json
        if FEEDBACK_PATH.exists():
            with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
                fb = json.load(f)
            fb = [e for e in fb if e.get("comment") != "测试反馈"]
            with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
                json.dump(fb, f, ensure_ascii=False, indent=2)
