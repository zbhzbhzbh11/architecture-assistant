"""内存缓存 — 基于 dict + TTL 的线程安全缓存.

【为什么缓存是请求级而不是会话级】
缓存键 = SHA-256(需求文本 + LLM模型名), 相同需求+相同模型 → 命中.
TTL 默认 1 小时, 之后自动失效. 这避免了对完全相同需求的重复 LLM 调用.

【线程安全】
使用 threading.Lock 保护 _store 字典的读写.
写时复制策略: get/set/clear/stats 都在锁内操作.

【环境变量】
  CACHE_ENABLED=false → 禁用缓存 (所有 get 返回 None)
  CACHE_TTL_SECONDS=3600 → 默认 1 小时
  CACHE_BACKEND=sqlite → 切换到 SQLite 持久化缓存 (跨重启保留)
"""

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("cache.memory")

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").strip().lower() != "false"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

# 内部状态 — 锁保护下的 dict + 统计计数
_lock = threading.Lock()
_store: Dict[str, Dict[str, Any]] = {}
_hits = 0
_misses = 0
_sets = 0
_clears = 0


def _now() -> float:
    return time.monotonic()


def _is_expired(entry: Dict[str, Any]) -> bool:
    """TTL 过期检查 — 超过 CACHE_TTL_SECONDS 自动失效."""
    return (_now() - entry["_ts"]) > CACHE_TTL_SECONDS


def get(key: str) -> Optional[Any]:
    """获取缓存 — 过期或未命中返回 None."""
    global _hits, _misses
    if not CACHE_ENABLED:
        _misses += 1
        return None
    with _lock:
        entry = _store.get(key)
        if entry is None:
            _misses += 1
            return None
        if _is_expired(entry):  # 惰性过期 — 读到过期条目时才清理
            del _store[key]
            _misses += 1
            return None
        _hits += 1
        return entry["_value"]


def set(key: str, value: Any) -> None:
    """写入缓存 — 带时间戳 (_ts) 用于 TTL."""
    global _sets
    if not CACHE_ENABLED:
        return
    with _lock:
        _store[key] = {"_value": value, "_ts": _now()}
        _sets += 1


def clear() -> int:
    """清空所有条目, 返回清除数 — 前端 /cache/clear 调用."""
    global _clears
    with _lock:
        count = len(_store)
        _store.clear()
        _clears += 1
    logger.info(f"Cache cleared: {count} entries")
    return count


def stats() -> Dict[str, Any]:
    """返回缓存统计 — 前端 /cache/stats 调用."""
    with _lock:
        total = _hits + _misses
        hit_rate = round(_hits / total, 4) if total > 0 else 0.0
        return {
            "backend": "memory",
            "enabled": CACHE_ENABLED,
            "ttl_seconds": CACHE_TTL_SECONDS,
            "entries": len(_store),
            "hits": _hits,
            "misses": _misses,
            "hit_rate": hit_rate,
            "sets": _sets,
            "clears": _clears,
        }
