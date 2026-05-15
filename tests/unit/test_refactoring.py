"""重构建议模块单元测试."""

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "services"))

from refactoring_agent.app.main import detect_smells, select_patterns, build_rule_template


def test_detect_smells_monolith():
    """单体系统需求应检测到相关坏味."""
    req = "已有单体电商系统，订单库存耦合严重，性能瓶颈明显，希望拆分。"
    features = {"high_concurrency": True, "scalability": True}
    smells = detect_smells(req, features)
    names = {s["name_zh"] for s in smells}
    assert len(smells) >= 2
    assert "单体耦合过重" in names or "扩展瓶颈" in names


def test_detect_smells_legacy():
    """遗留系统需求应检测到遗留系统锁定."""
    req = "遗留系统需要现代化改造，技术栈老旧，需要重构。"
    smells = detect_smells(req, {})
    assert any("遗留系统" in s["name_zh"] for s in smells)


def test_detect_smells_normal():
    """普通新系统需求不应检测到重构坏味."""
    req = "开发一个新的在线教育平台，支持直播和互动。"
    smells = detect_smells(req, {"real_time": True})
    assert len(smells) == 0


def test_select_patterns_strangler():
    """单体拆分需求应推荐绞杀者模式."""
    patterns = select_patterns("已有单体系统，订单库存耦合严重", {}, "Microservices")
    names = {p["name_zh"] for p in patterns}
    assert "绞杀者模式" in names


def test_select_patterns_acl():
    """遗留系统应推荐防腐层."""
    patterns = select_patterns("遗留系统需要与新的微服务平台集成", {}, "Microservices")
    names = {p["name_zh"] for p in patterns}
    assert "防腐层模式" in names


def test_build_template_refactoring_needed():
    """重构需求应返回 refactoring_needed=true."""
    smells = [{"name_zh": "单体耦合过重", "description": "业务耦合"}]
    patterns = [{
        "name": "Strangler Fig Pattern",
        "name_zh": "绞杀者模式",
        "when": "从单体迁移到微服务",
    }]
    result = build_rule_template(
        "已有单体系统需要拆分为微服务",
        smells, patterns,
        "Microservices", {},
    )
    assert result["refactoring_needed"] is True
    assert len(result["migration_steps"]) > 0
    assert len(result["risks"]) > 0
    assert len(result["mitigation_suggestions"]) > 0


def test_build_template_normal_system():
    """普通新系统应返回 refactoring_needed=false."""
    result = build_rule_template(
        "开发新的即时通讯系统",
        [], [], "Event-Driven Architecture", {},
    )
    assert result["refactoring_needed"] is False
    assert "target_architecture" in result


def test_template_includes_security_advice():
    """安全特征需求应包含权限和审计建议."""
    smells = [{"name_zh": "遗留系统锁定", "description": "遗留系统"}]
    result = build_rule_template(
        "政务系统私有化部署，需要安全隔离",
        smells, [],
        "Layered Architecture", {},
        features={"security": True},
    )
    assert any("权限" in s or "审计" in s for s in result["mitigation_suggestions"])


def test_template_strict_consistency_warning():
    """强一致需求应包含不要盲目拆分的警告."""
    smells = [{"name_zh": "单体耦合过重", "description": "耦合"}]
    result = build_rule_template(
        "银行核心账务系统需要重构",
        smells, [],
        "Microservices", {},
        features={"strict_consistency": True},
    )
    assert any("不要盲目拆分" in r or "ACID" in r for r in result["risks"])


def test_template_migration_steps():
    """迁移步骤应有具体工程化步骤."""
    smells = [{"name_zh": "单体耦合过重", "description": "."}]
    patterns = [{
        "name": "Strangler Fig Pattern",
        "name_zh": "绞杀者模式",
        "when": "test",
        "steps": ["1. 识别业务边界", "2. 建立网关路由", "3. 逐步迁移"],
    }]
    result = build_rule_template("test", smells, patterns, "Microservices", {})
    steps = result["migration_steps"]
    assert any("业务边界" in s or "网关" in s for s in steps)
