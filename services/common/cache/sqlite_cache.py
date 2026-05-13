"""SQLite 持久化缓存 — 跨服务重启保留缓存.

线程安全, 自动建表. 与 simple_cache 接口兼容.
用于 CACHE_BACKEND=sqlite 时替换内存缓存.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("cache.sqlite")

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").strip().lower() != "false"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
DB_PATH = os.getenv("CACHE_DB_PATH", "/tmp/architecture_cache.db")

_lock = threading.Lock()
_initialized = False

# 统计
_hits = 0
_misses = 0
_sets = 0
_clears = 0


def _init_db() -> None:
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON cache(created_at)")
        conn.commit()
        conn.close()
        _initialized = True
        logger.info(f"SQLite cache initialized at {DB_PATH}")


def _now() -> float:
    return time.time()


def _cleanup_expired() -> None:
    """清理过期条目."""
    cutoff = _now() - CACHE_TTL_SECONDS
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get(key: str) -> Optional[Any]:
    global _hits, _misses
    if not CACHE_ENABLED:
        _misses += 1
        return None
    _init_db()
    cutoff = _now() - CACHE_TTL_SECONDS
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT value FROM cache WHERE key = ? AND created_at > ?",
            (key, cutoff),
        ).fetchone()
        conn.close()
        if row:
            _hits += 1
            return json.loads(row[0])
        _misses += 1
        return None
    except Exception as e:
        logger.error(f"SQLite get error: {e}")
        _misses += 1
        return None


def set(key: str, value: Any) -> None:
    global _sets
    if not CACHE_ENABLED:
        return
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), _now()),
        )
        conn.commit()
        conn.close()
        _sets += 1
        # 定期清理过期条目
        if _sets % 100 == 0:
            _cleanup_expired()
    except Exception as e:
        logger.error(f"SQLite set error: {e}")


def clear() -> int:
    global _clears
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT count(*) FROM cache").fetchone()[0]
        conn.execute("DELETE FROM cache")
        conn.commit()
        conn.close()
        _clears += 1
        logger.info(f"SQLite cache cleared: {count} entries")
        return count
    except Exception as e:
        logger.error(f"SQLite clear error: {e}")
        return 0


def stats() -> Dict[str, Any]:
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT count(*) FROM cache").fetchone()[0]
        conn.close()
    except Exception:
        count = 0

    total = _hits + _misses
    hit_rate = round(_hits / total, 4) if total > 0 else 0.0
    return {
        "backend": "sqlite",
        "db_path": DB_PATH,
        "enabled": CACHE_ENABLED,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "entries": count,
        "hits": _hits,
        "misses": _misses,
        "hit_rate": hit_rate,
        "sets": _sets,
        "clears": _clears,
    }
