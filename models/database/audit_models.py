"""审查域表模型：审查记录 / 违规项 / 审查报告。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.constants import (
    AgentName,
    AuditConclusion,
    InspectionStatus,
    ReportStatus,
    ViolationSeverity,
    ViolationStatus,
)
from common.ids import inspection_id, report_id, violation_id
from common.timeutils import utc_now
from models.database.base import (
    Base,
    IDMixin,
    TenantMixin,
    TimestampMixin,
    enum_column,
)


class InspectionTable(TenantMixin, IDMixin, Base):
    """审查记录表。"""

    __tablename__ = "inspections"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: inspection_id()
    )
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=False, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("construction_plans.id"), index=True
    )
    agent: Mapped[str] = mapped_column(enum_column(AgentName), nullable=False)
    status: Mapped[str] = mapped_column(
        enum_column(InspectionStatus), nullable=False, default=InspectionStatus.PENDING.value
    )
    conclusion: Mapped[str | None] = mapped_column(enum_column(AuditConclusion))
    summary: Mapped[str | None] = mapped_column(Text)
    report_id: Mapped[str | None] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    violations: Mapped[list[ViolationTable]] = relationship(back_populates="inspection")


class ViolationTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """违规项表。

    regulation_version 落库为可追溯快照：审查类违规项该列必须非空
    （应用层以 RegulationVersionMissingError 强制约束）。
    """

    __tablename__ = "violations"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: violation_id()
    )
    inspection_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("inspections.id"), nullable=False, index=True
    )
    regulation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    regulation_version: Mapped[str | None] = mapped_column(String(64))
    clause: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        enum_column(ViolationSeverity), nullable=False, default=ViolationSeverity.MEDIUM.value
    )
    status: Mapped[str] = mapped_column(
        enum_column(ViolationStatus), nullable=False, default=ViolationStatus.OPEN.value
    )
    rectification: Mapped[str | None] = mapped_column(Text)

    inspection: Mapped[InspectionTable] = relationship(back_populates="violations")


class ReviewReportTable(TenantMixin, IDMixin, TimestampMixin, Base):
    """审查报告表（签章后正文不可变）。"""

    __tablename__ = "review_reports"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: report_id()
    )
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=False, index=True
    )
    inspection_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("inspections.id"), nullable=False
    )
    agent: Mapped[str] = mapped_column(enum_column(AgentName), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    conclusion: Mapped[str] = mapped_column(enum_column(AuditConclusion), nullable=False)
    # 法规ID -> 版本 快照（合规报告可追溯）
    regulation_versions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    signature: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        enum_column(ReportStatus), nullable=False, default=ReportStatus.DRAFT.value
    )
