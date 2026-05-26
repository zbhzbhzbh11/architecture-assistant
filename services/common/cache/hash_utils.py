"""缓存键生成 — SHA-256 请求级/Prompt级/评估级缓存键 + 知识库版本指纹.

【三种缓存键】
  cache_key()       — 请求级缓存: requirement + model + knowledge_version
  prompt_key()      — Prompt级缓存: prompt + model + knowledge_version
  candidates_key()  — 评估级缓存: requirement + candidates + model + knowledge_version

【knowledge_version() 作用】
版本指纹作为自动缓存失效信号: 知识库数据 (10种风格 JSON) 变更时
MD5 哈希值自动变化, 所有缓存键包含的版本号不匹配 → 旧缓存全部失效.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _get_knowledge_version() -> str:
    """环境变量优先, 否则 architecture_styles.json 的 MD5 前 8 位."""
    env_version = os.getenv("KNOWLEDGE_VERSION", "").strip()
    if env_version:
        return env_version
    styles_path = Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "data" / "architecture_styles.json"
    try:
        with open(styles_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except Exception:
        return "unknown"


def knowledge_version() -> str:
    """知识库版本指纹 — 缓存的版本标签."""
    return _get_knowledge_version()


def cache_key(requirement: str, model: str = "", prefix: str = "req") -> str:
    """请求级缓存键 — SHA-256(prefix|requirement|model|version)[:16].

    API Gateway recommend() 使用此键做请求级缓存.
    """
    kv = knowledge_version()
    raw = f"{prefix}|{requirement}|{model}|{kv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def prompt_key(prompt: str, model: str = "", prefix: str = "prompt") -> str:
    """LLM prompt 级缓存键 — 相同 prompt + 相同 model → 命中."""
    kv = knowledge_version()
    raw = f"{prefix}|{model}|{kv}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def candidates_key(requirement: str, candidates_json: str, model: str = "", prefix: str = "eval") -> str:
    """评估级缓存键 — requirement + candidates + model 的组合."""
    kv = knowledge_version()
    raw = f"{prefix}|{requirement}|{candidates_json}|{model}|{kv}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
