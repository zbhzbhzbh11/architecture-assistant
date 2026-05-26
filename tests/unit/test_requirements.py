import asyncio
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

# 确保 services/ 在 sys.path 中 (本地开发)
_SERVICES_ROOT = Path(__file__).resolve().parent.parent.parent / "services"
if str(_SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICES_ROOT))

from services.requirements_agent.app.main import extract, ExtractRequest


def test_extract_basic():
    payload = ExtractRequest(requirement="我们需要一个高并发且实时性要求高的 IM 系统。")
    result = asyncio.run(extract(payload))

    assert result.features["high_concurrency"] is True
    assert result.features["real_time"] is True
    assert "高并发" in result.feature_hits["high_concurrency"]
    assert "实时" in result.feature_hits["real_time"]


def test_extract_negative():
    payload = ExtractRequest(requirement="这是一个普通的离线管理系统，没有特殊要求。")
    result = asyncio.run(extract(payload))

    assert result.features["high_concurrency"] is False
    assert result.features["real_time"] is False


def test_extract_security():
    """验证安全性特征提取（P0 修复验证）."""
    payload = ExtractRequest(requirement="政务系统需要安全隔离、审计和权限控制。")
    result = asyncio.run(extract(payload))

    assert result.features["security"] is True
    assert any("安全" in h or "审计" in h or "权限" in h for h in result.feature_hits["security"])


def test_extract_negation():
    """否定语义过滤：'不需要高并发'不应命中."""
    payload = ExtractRequest(requirement="这是一个简单的内容管理系统，不需要高并发，没有实时性需求。")
    result = asyncio.run(extract(payload))

    assert result.features["high_concurrency"] is False, f"否定语义应过滤高并发: {result.feature_hits['high_concurrency']}"
    assert result.features["real_time"] is False


# ── Few-shot Prompt 测试 ──────────────────────────────────────

def test_few_shot_prompt_contains_examples():
    """few-shot prompt 应包含 6 个示例的关键词."""
    from common.prompts.requirements_few_shot import build_few_shot_prompt
    prompt = build_few_shot_prompt("系统需要处理大量并发请求")

    assert "示例1" in prompt
    assert "示例6" in prompt
    assert "双十一" in prompt or "TB" in prompt or "ACID" in prompt  # 示例中的领域术语
    assert "高并发" in prompt
    assert "安全" in prompt or "医疗数据" in prompt


def test_few_shot_prompt_includes_requirement():
    """few-shot prompt 末尾应包含用户需求."""
    from common.prompts.requirements_few_shot import build_few_shot_prompt
    user_req = "一个银行对账系统需要高可靠和强一致"
    prompt = build_few_shot_prompt(user_req)

    assert user_req in prompt
    assert "JSON" in prompt


def test_few_shot_prompt_json_constraint():
    """few-shot prompt 应保留 JSON-only 输出约束."""
    from common.prompts.requirements_few_shot import build_few_shot_prompt
    prompt = build_few_shot_prompt("测试需求")
    assert "JSON" in prompt
    assert "不要输出其他内容" in prompt


def test_few_shot_has_twelve_examples():
    """验证 few-shot 模块恰含 12 个示例 (覆盖全部 12 个维度)."""
    from common.prompts.requirements_few_shot import EXAMPLES, FEATURE_LABELS_ZH
    assert len(EXAMPLES) == 12
    # 验证每个维度至少有一个正面示例
    covered = set()
    for _, labels in EXAMPLES:
        for k, v in labels.items():
            if v:
                covered.add(k)
    assert covered == set(FEATURE_LABELS_ZH.keys()), f"Missing: {set(FEATURE_LABELS_ZH.keys()) - covered}"
