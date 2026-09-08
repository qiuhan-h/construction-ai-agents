"""安全审计日志表模型（7a-5 安全加固）。

记录 API 请求的审计轨迹：tenant_id + actor + action + resource。
用于生产环境的合规审计与安全追溯。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from common.timeutils import utc_now
from models.database.base import Base, IDMixin, TenantMixin


class SecurityAuditLogTable(TenantMixin, IDMixin, Base):
    """安全审计日志表。

    字段说明：
    - tenant_id：租户 ID（来自 TenantMixin）
    - actor：操作者标识（用户 ID 或 system）
    - action：操作类型（如 login / create / update / delete / export）
    - resource：请求资源路径（如 /api/v1/agents/xxx）
    - method：HTTP 方法（GET / POST / PUT / DELETE）
    - status_code：响应状态码
    - ip：客户端 IP
    - detail：附加详情（JSON，如请求体摘要、变更前后快照）
    """

    __tablename__ = "security_audit_logs"

    actor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(512), nullable=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
