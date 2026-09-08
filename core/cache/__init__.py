"""缓存包：Redis 缓存（regulation / case 热数据）。

dev 环境降级为进程内字典缓存；prod 由 REDIS_URL 启用真实 Redis。
"""

from __future__ import annotations
