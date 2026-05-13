"""缓存键生成 — 对 requirement、prompt、model、knowledge_version 生成稳定 hash."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _get_knowledge_version() -> str:
    """获取知识库版本: 环境变量优先, 否则用 styles 文件内容 hash."""
    env_version = os.getenv("KNOWLEDGE_VERSION", "").strip()
    if env_version:
        return env_version
    # 从 architecture_styles.json 计算内容 hash
    styles_path = Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "data" / "architecture_styles.json"
    try:
        with open(styles_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except Exception:
        return "unknown"


def knowledge_version() -> str:
    """对外暴露的知识库版本, 带缓存避免重复读文件."""
    return _get_knowledge_version()


def cache_key(requirement: str, model: str = "", prefix: str = "req") -> str:
    """生成请求级缓存键.

    key = sha256(prefix + requirement + model + knowledge_version)[:16]
    """
    kv = knowledge_version()
    raw = f"{prefix}|{requirement}|{model}|{kv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def prompt_key(prompt: str, model: str = "", prefix: str = "prompt") -> str:
    """生成 LLM prompt 级缓存键."""
    kv = knowledge_version()
    raw = f"{prefix}|{model}|{kv}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def candidates_key(requirement: str, candidates_json: str, model: str = "", prefix: str = "eval") -> str:
    """生成 evaluation 缓存键 (需求 + 候选 + 模型)."""
    kv = knowledge_version()
    raw = f"{prefix}|{requirement}|{candidates_json}|{model}|{kv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
