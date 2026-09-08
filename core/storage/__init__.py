"""core.storage：仓储层与对象存储适配。

子模块：
- ``base``           Protocol / 异常
- ``local_storage``  本地文件系统存储（4d 占位；5b 待补）
- ``object_storage`` 对象存储（OSS / MinIO；4d 占位；5b 待补）
- ``sqlalchemy_repos`` SQLAlchemy ORM 业务仓储（5b.3 新增）
"""

from __future__ import annotations

from core.storage.base import (
    BackendUnavailableError,
    Repository,
    RepositoryError,
)

__all__ = [
    "BackendUnavailableError",
    "Repository",
    "RepositoryError",
]
