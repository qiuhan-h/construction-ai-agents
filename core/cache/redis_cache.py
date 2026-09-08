"""Redis 缓存实现（regulation / case 热数据）。

dev 环境降级为进程内字典；prod 由 REDIS_URL 启用真实 Redis。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("core.cache.redis_cache")

_redis_client: Any = None
_local_cache: dict[str, tuple[Any, float]] = {}


def _get_redis() -> Any:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis
        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis 缓存已连接: %s", url.split("@")[-1] if "@" in url else "localhost")
    except ImportError:
        logger.warning("redis 未安装 → 降级为进程内字典缓存")
        _redis_client = None
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis 连接失败: %s → 降级为进程内字典缓存", e)
        _redis_client = None
    return _redis_client


class RedisCache:
    """缓存读写：Redis 优先，降级字典。"""

    async def get(self, key: str) -> Any:
        client = _get_redis()
        if client is not None:
            raw = client.get(key)
            if raw:
                return json.loads(raw)
            return None
        entry = _local_cache.get(key)
        if entry and entry[1] > time.time():
            return entry[0]
        _local_cache.pop(key, None)
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        client = _get_redis()
        raw = json.dumps(value, ensure_ascii=False, default=str)
        if client is not None:
            client.setex(key, ttl, raw)
        else:
            _local_cache[key] = (value, time.time() + ttl)

    async def delete(self, key: str) -> None:
        client = _get_redis()
        if client is not None:
            client.delete(key)
        else:
            _local_cache.pop(key, None)


_cache: RedisCache | None = None


def get_cache() -> RedisCache:
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache
