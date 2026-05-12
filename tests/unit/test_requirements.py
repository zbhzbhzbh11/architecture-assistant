import asyncio
import pytest
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
