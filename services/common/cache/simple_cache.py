"""内存缓存 — 基于 dict + TTL 的简单缓存实现.

支持 get/set/clear/stats 操作. 超过 TTL 的条目自动失效.
线程安全: 使用简单的写时复制策略 (非高性能场景).

环境变量:
  CACHE_ENABLED=true/false (默认 true)
  CACHE_TTL_SECONDS=3600 (默认)
"""

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("cache.memory")

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").strip().lower() != "false"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

_lock = threading.Lock()
_store: Dict[str, Dict[str, Any]] = {}

# 统计
_hits = 0
_misses = 0
_sets = 0
_clears = 0


def _now() -> float:
    return time.monotonic()


def _is_expired(entry: Dict[str, Any]) -> bool:
    return (_now() - entry["_ts"]) > CACHE_TTL_SECONDS


def get(key: str) -> Optional[Any]:
    """获取缓存条目. 过期返回 None."""
    global _hits, _misses
    if not CACHE_ENABLED:
        _misses += 1
        return None
    with _lock:
        entry = _store.get(key)
        if entry is None:
            _misses += 1
            return None
        if _is_expired(entry):
            del _store[key]
            _misses += 1
            return None
        _hits += 1
        return entry["_value"]


def set(key: str, value: Any) -> None:
    """写入缓存条目."""
    global _sets
    if not CACHE_ENABLED:
        return
    with _lock:
        _store[key] = {"_value": value, "_ts": _now()}
        _sets += 1


def clear() -> int:
    """清空缓存, 返回清除条目数."""
    global _clears
    with _lock:
        count = len(_store)
        _store.clear()
        _clears += 1
    logger.info(f"Cache cleared: {count} entries")
    return count


def stats() -> Dict[str, Any]:
    """返回缓存统计."""
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
