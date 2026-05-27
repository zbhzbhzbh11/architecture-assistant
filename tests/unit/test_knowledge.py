"""知识库模块单元测试.

覆盖:
  - JSON 文件存储 (fallback 路径)
  - Neo4j 图存储 (可选, Neo4j 不可用时自动跳过)
  - /graph/status 端点
  - 后端切换逻辑
"""

import os
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# ── Mock missing modules before importing services ──
if 'httpx' not in sys.modules:
    _httpx_mock = MagicMock()
    _httpx_mock.HTTPStatusError = type('HTTPStatusError', (Exception,), {})
    _httpx_mock.AsyncClient = MagicMock()
    _httpx_mock.Response = MagicMock()
    sys.modules['httpx'] = _httpx_mock
for _mod in ('fastapi', 'fastapi.middleware', 'fastapi.middleware.cors'):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.knowledge_base.app.main import (
    load_styles, add_style, add_feedback, get_feedback_stats,
    StylePayload, FeedbackPayload, save_styles, FEEDBACK_PATH,
)
from services.knowledge_base.app.json_repository import JsonRepository
from services.knowledge_base.app.graph_repository import GraphRepository
from services.knowledge_base.app.main import ADRPayload


# ── 辅助: 检测 Neo4j 是否可用 ──────────────────────────────────

def _neo4j_available() -> bool:
    """检测 Neo4j 是否可达."""
    try:
        from neo4j import GraphDatabase
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "neo4jneo4j")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


NEO4J_SKIP_REASON = "Neo4j not available"
neo4j_required = pytest.mark.skipif(not _neo4j_available(), reason=NEO4J_SKIP_REASON)


# ── JSON 存储测试 (始终运行) ───────────────────────────────────

class TestKnowledgeBaseLoad:
    """知识库加载与数据完整性测试 (JSON fallback)."""

    def test_styles_count_at_least_10(self):
        data = load_styles()
        styles = data["styles"]
        assert len(styles) >= 10, f"架构风格数量不足: {len(styles)} < 10"

    def test_each_style_has_required_fields(self):
        data = load_styles()
        required = {"name", "tags", "best_for", "pros", "cons"}
        for style in data["styles"]:
            missing = required - set(style.keys())
            name = style.get("name", "?")
            assert not missing, f"{name}: 缺少字段 {missing}"

    def test_contains_mainstream_styles(self):
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
        data = load_styles()
        for style in data["styles"]:
            topo = style.get("topology_mermaid", "")
            name = style.get("name", "?")
            assert topo, f"{name}: 缺少 topology_mermaid"

    def test_pros_cons_non_empty(self):
        data = load_styles()
        for style in data["styles"]:
            name = style.get("name", "?")
            assert len(style.get("pros", [])) > 0, f"{name}: pros 为空"
            assert len(style.get("cons", [])) > 0, f"{name}: cons 为空"


class TestKnowledgeExtension:
    """知识库扩展接口测试 (JSON)."""

    def test_add_style(self):
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

        # 清理
        after["styles"] = [s for s in after["styles"] if s["name"] != "Test Style"]
        save_styles(after)


class TestFeedback:
    """案例学习反馈接口测试 (JSON)."""

    def test_add_and_stats(self):
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

        # 清理
        if FEEDBACK_PATH.exists():
            with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
                fb = json.load(f)
            fb = [e for e in fb if e.get("comment") != "测试反馈"]
            with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
                json.dump(fb, f, ensure_ascii=False, indent=2)


# ── JSON Repository 直接测试 ───────────────────────────────────

class TestJsonRepository:
    """直接测试 JsonRepository 方法."""

    def test_get_styles_returns_dict(self):
        result = JsonRepository.get_styles()
        assert "styles" in result
        assert isinstance(result["styles"], list)
        assert len(result["styles"]) >= 10

    def test_graph_status_json(self):
        status = JsonRepository.graph_status()
        assert status["backend"] == "json"
        assert status["neo4j_available"] is False
        assert status["node_count"] >= 10

    def test_get_feedback(self):
        result = JsonRepository.get_feedback()
        assert "feedback" in result
        assert isinstance(result["feedback"], list)

    def test_get_learned_weights(self):
        result = JsonRepository.get_learned_weights()
        assert "weights" in result
        assert "total_feedback_learned" in result


# ── Graph Status 端点测试 (始终运行, 不依赖 Neo4j) ─────────────

class TestGraphStatusEndpoint:
    """测试 /graph/status 端点 (使用默认 JSON backend)."""

    def test_graph_status_returns_backend_field(self):
        status = JsonRepository.graph_status()
        assert "backend" in status
        assert status["backend"] in ("json", "neo4j")
        assert "neo4j_available" in status
        assert "node_count" in status

    def test_json_fallback_is_always_available(self):
        """验证 JSON fallback 在任何情况下都可用."""
        result = load_styles()
        assert "styles" in result
        assert len(result["styles"]) >= 10


# ── Neo4j 图存储测试 (仅 Neo4j 可用时运行) ─────────────────────

@pytest.mark.integration
class TestGraphRepository:
    """Neo4j 图存储测试 — 仅当 Neo4j 可用时运行."""

    @neo4j_required
    def test_graph_status_neo4j(self):
        status = GraphRepository.graph_status()
        assert status["neo4j_available"] is True
        assert status["backend"] == "neo4j"

    @neo4j_required
    def test_get_styles_from_neo4j(self):
        result = GraphRepository.get_styles()
        assert result is not None
        assert "styles" in result
        assert len(result["styles"]) >= 1

    @neo4j_required
    def test_graph_status_has_counts(self):
        status = GraphRepository.graph_status()
        if status["neo4j_available"]:
            assert status["node_count"] >= 1
            assert "relationship_count" in status


# ── ADR 存储与查询测试 ────────────────────────────────────────

class TestADR:
    """ADR (Architecture Decision Record) 存储和查询测试."""

    def test_create_adr(self):
        """POST /adr 应返回 adr_id 和 status."""
        payload = ADRPayload(
            requirement="测试需求：高并发实时消息系统",
            extracted_features={"high_concurrency": True, "real_time": True},
            candidates=[
                {"style": "Event-Driven Architecture", "score": 8},
                {"style": "Microservices", "score": 5},
            ],
            recommended_style="Event-Driven Architecture",
            recommended_style_zh="事件驱动架构",
            alternative_styles=["Microservices"],
            decision_basis={"rule_engine": ["高并发场景处理能力强"], "llm_summary": "推荐事件驱动..."},
            risk_and_suggestions={"main_risks": ["复杂度高"], "suggestions": ["引入消息队列"]},
        )
        result = JsonRepository.add_adr(payload.model_dump())
        assert result["status"] == "ok"
        assert "adr_id" in result
        assert result["adr_id"].startswith("ADR-")
        assert result["total"] >= 1

    def test_list_adrs(self):
        """GET /adr 应返回列表."""
        result = JsonRepository.get_adrs(limit=10)
        assert "adrs" in result
        assert "total" in result
        assert result["total"] >= 1

    def test_get_adr_by_id(self):
        """GET /adr/{id} 应返回对应 ADR."""
        list_result = JsonRepository.get_adrs(limit=50)
        if list_result["total"] > 0:
            adr_id = list_result["adrs"][-1]["adr_id"]
            adr = JsonRepository.get_adr(adr_id)
            assert adr is not None
            assert adr["adr_id"] == adr_id
            assert "recommended_style" in adr

    def test_adr_contains_required_fields(self):
        """ADR 应包含必填字段: requirement, features, candidates, recommended_style, timestamp."""
        list_result = JsonRepository.get_adrs(limit=50)
        if list_result["total"] > 0:
            adr = list_result["adrs"][-1]
            assert "requirement" in adr
            assert "extracted_features" in adr
            assert "candidates" in adr
            assert "recommended_style" in adr
            assert "decision_basis" in adr
            assert "timestamp" in adr
            assert "risk_and_suggestions" in adr

    def test_adr_style_consistency(self):
        """ADR 中 recommended_style 应与原始记录一致."""
        list_result = JsonRepository.get_adrs(limit=50)
        if list_result["total"] > 0:
            adr = list_result["adrs"][-1]
            assert adr["recommended_style"] == "Event-Driven Architecture"

    def test_get_nonexistent_adr(self):
        """不存在的 ADR 应返回 None."""
        result = JsonRepository.get_adr("ADR-nonexistent-999")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# 知识进化 (反馈 + 权重) 单元测试
# ═══════════════════════════════════════════════════════════════

import math
from datetime import datetime, timedelta, timezone
from services.knowledge_base.app.graph_repository import (
    _decay_weight, _normalize_weights,
)


class TestTimeDecay:
    """时间衰减机制 — _decay_weight()."""

    def test_fresh_feedback_full_weight(self):
        """今天的反馈衰减因子 = 1.0 (无衰减)."""
        ts = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        assert _decay_weight(ts) == pytest.approx(1.0, abs=0.001)

    def test_old_feedback_decayed(self):
        """30 天前的反馈: e^(-0.05*30) = e^(-1.5) ≈ 0.223."""
        old = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)).isoformat()
        assert _decay_weight(old) == pytest.approx(0.223, abs=0.01)

    def test_very_old_feedback_near_zero(self):
        """365 天前的反馈: e^(-0.05*365) = e^(-18.25) ≈ 1.18e-8, 趋近于 0."""
        ancient = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=365)).isoformat()
        w = _decay_weight(ancient)
        assert w < 0.001, f"1年前的权重应趋近于0, 实际 {w}"

    def test_no_timestamp_defaults_to_one(self):
        """无时间戳时默认为 1.0."""
        assert _decay_weight(None) == 1.0
        assert _decay_weight("") == 1.0

    def test_invalid_timestamp_defaults_to_one(self):
        """无效时间戳默认为 1.0."""
        assert _decay_weight("not-a-date") == 1.0

    def test_old_less_than_new(self):
        """旧反馈的衰减因子应严格小于新反馈."""
        ts_old = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)).isoformat()
        ts_new = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).isoformat()
        assert _decay_weight(ts_old) < _decay_weight(ts_new)


class TestNormalizeWeights:
    """特征级 max-normalization — _normalize_weights()."""

    def test_single_style_gets_one(self):
        """单个风格 → 归一化为 1.0."""
        raw = {"high_concurrency": {"Event-Driven Architecture": 4.0}}
        result = _normalize_weights(raw)
        assert result["high_concurrency"]["Event-Driven Architecture"] == 1.0

    def test_two_styles_max_normalized(self):
        """两个风格: 高分=1.0, 低分=比例."""
        raw = {"high_concurrency": {
            "Event-Driven Architecture": 4.0,
            "Microservices": 2.0,
        }}
        result = _normalize_weights(raw)
        assert result["high_concurrency"]["Event-Driven Architecture"] == 1.0
        assert result["high_concurrency"]["Microservices"] == 0.5

    def test_feature_isolation(self):
        """不同特征的归一化互不影响."""
        raw = {
            "high_concurrency": {"Event-Driven": 4.0, "Microservices": 1.0},
            "simple_crud": {"Layered": 2.0},
        }
        result = _normalize_weights(raw)
        # high_concurrency 归一化
        assert result["high_concurrency"]["Event-Driven"] == 1.0
        assert result["high_concurrency"]["Microservices"] == 0.25
        # simple_crud 独立归一化 (不受 high_concurrency 影响)
        assert result["simple_crud"]["Layered"] == 1.0

    def test_tie_scores(self):
        """两个风格同分 → 都是 1.0."""
        raw = {"reliability": {"Event-Driven": 3.0, "Microservices": 3.0}}
        result = _normalize_weights(raw)
        assert result["reliability"]["Event-Driven"] == 1.0
        assert result["reliability"]["Microservices"] == 1.0


class TestLearnedWeightsInScoring:
    """学习权重在评分中的应用 — score_style() Layer 2."""

    def test_strong_weight_adds_one(self):
        """weight >= 0.5 → +1 分."""
        from services.common.matching.rules import score_style

        style = {"name": "Event-Driven Architecture", "tags": [],
                 "pros": [], "cons": []}
        features = {"high_concurrency": True}
        learned = {"high_concurrency": {"Event-Driven Architecture": 0.85}}

        result = score_style(style, features, learned)
        assert result["score"] >= 1, f"weight=0.85 应加分, 实际 {result['score']}"
        assert any("学习权重" in r for r in result["reasons"])

    def test_medium_weight_adds_one(self):
        """weight >= 0.3 → +1 分."""
        from services.common.matching.rules import score_style

        style = {"name": "Event-Driven Architecture", "tags": [],
                 "pros": [], "cons": []}
        features = {"high_concurrency": True}
        learned = {"high_concurrency": {"Event-Driven Architecture": 0.35}}

        result = score_style(style, features, learned)
        assert result["score"] >= 1, f"weight=0.35 应加分, 实际 {result['score']}"
        assert any("学习权重(中)" in r for r in result["reasons"])

    def test_weak_weight_no_effect(self):
        """weight < 0.3 → 不加分."""
        from services.common.matching.rules import score_style

        style = {"name": "Event-Driven Architecture", "tags": [],
                 "pros": [], "cons": []}
        features = {"high_concurrency": True}
        learned = {"high_concurrency": {"Event-Driven Architecture": 0.15}}

        result = score_style(style, features, learned)
        assert not any("学习权重" in r for r in result["reasons"]), \
            f"weight=0.15 不应加分, reasons: {result['reasons']}"

    def test_unrelated_feature_not_affected(self):
        """无关特征的权重不影响当前评分 — 跨特征隔离."""
        from services.common.matching.rules import score_style

        style = {"name": "Serverless", "tags": ["scalability"],
                 "pros": [], "cons": []}
        features = {"scalability": True, "strict_consistency": True}
        # 只有 scalability 有权重, strict_consistency 没有
        learned = {"scalability": {"Serverless": 0.9}}

        result = score_style(style, features, learned)
        # 标签匹配: scalability +2 = 2
        # 学习权重: scalability 0.9>=0.5 → +1
        # strict_consistency 不在 learned_weights 中 → 不加
        # Serverless 没有特定规则触发
        assert result["score"] == 3, f"score 应为 3, 实际 {result['score']}"


class TestFeedbackWeightUpdate:
    """反馈写入 + 权重更新 — JSON fallback 路径."""

    def test_update_creates_new_feature_entry(self):
        """新特征的第一次反馈应创建权重条目."""
        from services.knowledge_base.app.json_repository import (
            _update_learned_weights, _load_weights, _save_weights,
        )
        import tempfile, json as _json
        from pathlib import Path as _Path

        # 使用临时文件避免污染真实数据
        orig_path = None
        try:
            from services.knowledge_base.app.json_repository import WEIGHTS_PATH
            orig_path = WEIGHTS_PATH
            # 备份原权重
            backup = _load_weights()
            # 用临时路径
            import services.knowledge_base.app.json_repository as jr
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            tf.close()
            _Path(tf.name).write_text("{}", encoding="utf-8")
            jr.WEIGHTS_PATH = _Path(tf.name)

            features = {"high_concurrency": True, "real_time": True}
            _update_learned_weights("测试需求", "Event-Driven Architecture", features)

            weights = _load_weights()
            assert "high_concurrency" in weights
            assert "real_time" in weights
            assert weights["high_concurrency"]["Event-Driven Architecture"] == 1
            assert weights["real_time"]["Event-Driven Architecture"] == 1

            # 清理
            _Path(tf.name).unlink()
        finally:
            if orig_path:
                import services.knowledge_base.app.json_repository as jr2
                jr2.WEIGHTS_PATH = orig_path

    def test_multiple_confirmations_accumulate(self):
        """多次确认同一风格 → 权重累加."""
        from services.knowledge_base.app.json_repository import (
            _update_learned_weights, _load_weights,
        )
        import tempfile
        from pathlib import Path as _Path

        orig_path = None
        try:
            from services.knowledge_base.app.json_repository import WEIGHTS_PATH
            orig_path = WEIGHTS_PATH
            import services.knowledge_base.app.json_repository as jr
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            tf.close()
            _Path(tf.name).write_text("{}", encoding="utf-8")
            jr.WEIGHTS_PATH = _Path(tf.name)

            features = {"high_concurrency": True}
            for _ in range(3):
                _update_learned_weights("高并发系统", "Event-Driven Architecture", features)

            weights = _load_weights()
            assert weights["high_concurrency"]["Event-Driven Architecture"] == 3

            _Path(tf.name).unlink()
        finally:
            if orig_path:
                import services.knowledge_base.app.json_repository as jr2
                jr2.WEIGHTS_PATH = orig_path

    def test_feature_isolation_in_update(self):
        """反馈特征A → 特征B的权重不变."""
        from services.knowledge_base.app.json_repository import (
            _update_learned_weights, _load_weights,
        )
        import tempfile
        from pathlib import Path as _Path

        orig_path = None
        try:
            from services.knowledge_base.app.json_repository import WEIGHTS_PATH
            orig_path = WEIGHTS_PATH
            import services.knowledge_base.app.json_repository as jr
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            tf.close()
            data = {"high_concurrency": {"Event-Driven Architecture": 0.85},
                    "simple_crud": {"Layered Architecture": 0.65}}
            _Path(tf.name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            jr.WEIGHTS_PATH = _Path(tf.name)

            # 只对 high_concurrency 提交反馈
            features = {"high_concurrency": True, "real_time": True}
            _update_learned_weights("高并发实时系统", "Event-Driven Architecture", features)

            weights = _load_weights()
            # simple_crud 的权重应保持不变
            assert weights["simple_crud"]["Layered Architecture"] == 0.65
            # high_concurrency 增加了
            assert weights["high_concurrency"]["Event-Driven Architecture"] > 0.85

            _Path(tf.name).unlink()
        finally:
            if orig_path:
                import services.knowledge_base.app.json_repository as jr2
                jr2.WEIGHTS_PATH = orig_path
