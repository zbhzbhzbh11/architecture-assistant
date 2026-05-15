"""重构建议端点集成测试 — 直接调用 handler 函数 (FastAPI 无副作用).

覆盖:
  - POST /refactor 正常路径 → smells + patterns + suggestions
  - POST /refactor + llm_polish 成功 → 验证字段被 LLM 替换
  - POST /refactor + llm_polish 失败 → 降级回规则模板
  - POST /refactor 正常输入无坏味 → refactoring_needed=false
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

# ── sys.modules mock (必须放在 import services 之前) ──
for _mod in ('httpx', 'fastapi', 'fastapi.middleware', 'fastapi.middleware.cors'):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
# httpx 的 HTTPStatusError 需为真实 Exception 子类
_hm = sys.modules['httpx']
_hm.HTTPStatusError = type('HTTPStatusError', (Exception,), {})
_hm.AsyncClient = MagicMock()
_hm.Response = MagicMock()

import pytest

_SR = Path(__file__).resolve().parent.parent.parent / "services"
if str(_SR) not in sys.path:
    sys.path.insert(0, str(_SR))

from refactoring_agent.app.main import refactor, RefactorRequest, llm_polish
import refactoring_agent.app.main as refactor_mod


MONOLITH_REQUIREMENT = (
    "已有单体电商系统，订单库存耦合严重，性能瓶颈明显，"
    "团队膨胀后发布周期长达两周，希望拆分为微服务架构。"
)

CLEAN_REQUIREMENT = "开发一个新的在线教育平台，支持课程直播和互动消息。"


# ====================================================================
# POST /refactor 端点测试
# ====================================================================

class TestRefactorNormalPath:
    """POST /refactor 正常路径."""

    def test_monolith_detects_smells_and_patterns(self):
        """单体耦合场景 → smells + patterns + migration_steps."""
        payload = RefactorRequest(
            requirement=MONOLITH_REQUIREMENT,
            features={"high_concurrency": True, "scalability": True},
            recommended_style="Microservices",
        )
        result = asyncio.run(refactor(payload))

        assert result["refactoring_needed"] is True
        assert len(result["detected_architecture_smells"]) >= 2, \
            f"应检测到 >= 2 个坏味: {result['detected_architecture_smells']}"
        assert len(result["suggested_patterns"]) >= 1
        assert len(result["migration_steps"]) >= 5
        assert len(result["risks"]) >= 1
        assert len(result["mitigation_suggestions"]) >= 1
        assert result["llm_polished"] is False  # LLM 未配置

    def test_clean_system_no_refactoring_needed(self):
        """正常新系统 → refactoring_needed=false, 通用步骤."""
        payload = RefactorRequest(
            requirement=CLEAN_REQUIREMENT,
            features={"real_time": True},
            recommended_style="Event-Driven Architecture",
        )
        result = asyncio.run(refactor(payload))

        assert result["refactoring_needed"] is False
        assert len(result["detected_architecture_smells"]) == 0
        assert len(result["migration_steps"]) >= 1  # 通用兜底步骤
        assert result["target_architecture"] == "Event-Driven Architecture"


# ====================================================================
# llm_polish 路径测试
# ====================================================================

class TestRefactorLLMPolish:
    """POST /refactor 含 LLM 润色路径."""

    def test_llm_polish_success_replaces_fields(self):
        """LLM 润色成功 → migration_steps / risks / mitigation 被替换."""
        payload = RefactorRequest(
            requirement=MONOLITH_REQUIREMENT,
            features={"high_concurrency": True},
            recommended_style="Microservices",
        )

        polished_data = {
            "migration_steps": ["Step A 润色版", "Step B 润色版"],
            "risks": ["风险描述已润色"],
            "mitigation_suggestions": ["缓解方案已润色"],
        }

        with patch.object(refactor_mod, 'LLM_API_BASE', 'http://mock'), \
             patch.object(refactor_mod, 'LLM_API_KEY', 'mock-key'), \
             patch.object(refactor_mod, 'LLM_MODEL', 'mock-model'), \
             patch("refactoring_agent.app.main.httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": '{"migration_steps":["Step A 润色版","Step B 润色版"],"risks":["风险描述已润色"],"mitigation_suggestions":["缓解方案已润色"]}'}}]
            }
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value.post.return_value = mock_resp
            mock_client.return_value = mock_instance

            result = asyncio.run(refactor(payload))

        assert result["llm_polished"] is True
        assert result["migration_steps"] == ["Step A 润色版", "Step B 润色版"]
        assert result["risks"] == ["风险描述已润色"]
        assert result["mitigation_suggestions"] == ["缓解方案已润色"]

    def test_llm_polish_failure_falls_back_template(self):
        """LLM 润色异常 → llm_polished=False, 保留规则模板输出."""
        payload = RefactorRequest(
            requirement=MONOLITH_REQUIREMENT,
            features={"high_concurrency": True},
            recommended_style="Microservices",
        )

        with patch.object(refactor_mod, 'LLM_API_BASE', 'http://mock'), \
             patch.object(refactor_mod, 'LLM_API_KEY', 'mock-key'), \
             patch.object(refactor_mod, 'LLM_MODEL', 'mock-model'), \
             patch("refactoring_agent.app.main.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value.post.side_effect = Exception("LLM connection refused")
            mock_client.return_value = mock_instance

            result = asyncio.run(refactor(payload))

        assert result["llm_polished"] is False
        assert result["refactoring_needed"] is True
        assert len(result["detected_architecture_smells"]) >= 2
        assert len(result["suggested_patterns"]) >= 1
        # 规则模板的步骤/风险/缓解仍存在
        assert len(result["migration_steps"]) >= 5
        assert len(result["risks"]) >= 1
        assert len(result["mitigation_suggestions"]) >= 1
