"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-03 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =====================================================
    # tenants
    # =====================================================
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("contact", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", "closed", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_tenants_code"),
    )

    # =====================================================
    # projects
    # =====================================================
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("address", sa.String(length=512), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "design", "construction", "completed", "suspended",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tenant_project_code"),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])

    # =====================================================
    # construction_plans
    # =====================================================
    op.create_table(
        "construction_plans",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "plan_type",
            sa.Enum(
                "scaffolding", "formwork", "deep_foundation_pit", "hoisting",
                "temp_electrical", "demolition", "other",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "submitted", "approved", "rejected",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_construction_plans_project_id_projects"
        ),
    )
    op.create_index(
        "ix_construction_plans_tenant_id", "construction_plans", ["tenant_id"]
    )
    op.create_index(
        "ix_construction_plans_project_id", "construction_plans", ["project_id"]
    )

    # =====================================================
    # inspections
    # =====================================================
    op.create_table(
        "inspections",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("plan_id", sa.String(length=32), nullable=True),
        sa.Column(
            "agent",
            sa.Enum(
                "orchestrator", "safety_audit_agent", "compliance_agent",
                "site_monitor_agent", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "completed", "failed",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "conclusion",
            sa.Enum(
                "pass", "conditional_pass", "fail",
                native_enum=False, length=32,
            ),
            nullable=True,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("report_id", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_inspections_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["construction_plans.id"], name="fk_inspections_plan_id_construction_plans"
        ),
    )
    op.create_index("ix_inspections_tenant_id", "inspections", ["tenant_id"])
    op.create_index("ix_inspections_project_id", "inspections", ["project_id"])
    op.create_index("ix_inspections_plan_id", "inspections", ["plan_id"])
    op.create_index("ix_inspections_report_id", "inspections", ["report_id"])

    # =====================================================
    # violations
    # =====================================================
    op.create_table(
        "violations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("inspection_id", sa.String(length=32), nullable=False),
        sa.Column("regulation_id", sa.String(length=64), nullable=True),
        sa.Column("regulation_version", sa.String(length=64), nullable=True),
        sa.Column("clause", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "low", "medium", "high", "critical",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "open", "rectifying", "closed", "waived",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("rectification", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["inspection_id"], ["inspections.id"], name="fk_violations_inspection_id_inspections"
        ),
    )
    op.create_index("ix_violations_tenant_id", "violations", ["tenant_id"])
    op.create_index("ix_violations_inspection_id", "violations", ["inspection_id"])
    op.create_index("ix_violations_regulation_id", "violations", ["regulation_id"])

    # =====================================================
    # review_reports
    # =====================================================
    op.create_table(
        "review_reports",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("inspection_id", sa.String(length=32), nullable=False),
        sa.Column(
            "agent",
            sa.Enum(
                "orchestrator", "safety_audit_agent", "compliance_agent",
                "site_monitor_agent", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "conclusion",
            sa.Enum(
                "pass", "conditional_pass", "fail",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("regulation_versions", sa.JSON(), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "signed", "final", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_review_reports_project_id_projects"
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"], ["inspections.id"], name="fk_review_reports_inspection_id_inspections"
        ),
    )
    op.create_index("ix_review_reports_tenant_id", "review_reports", ["tenant_id"])
    op.create_index("ix_review_reports_project_id", "review_reports", ["project_id"])
    op.create_index("ix_review_reports_inspection_id", "review_reports", ["inspection_id"])

    # =====================================================
    # alerts
    # =====================================================
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "level",
            sa.Enum("info", "warning", "critical", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("location", sa.JSON(), nullable=True),
        sa.Column("metric", sa.JSON(), nullable=True),
        sa.Column("dedup_key", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active", "acknowledged", "resolved",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_alerts_project_id_projects"
        ),
    )
    op.create_index("ix_alerts_tenant_id", "alerts", ["tenant_id"])
    op.create_index("ix_alerts_project_id", "alerts", ["project_id"])
    op.create_index("ix_alerts_dedup_key", "alerts", ["dedup_key"])
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"])

    # =====================================================
    # sensor_devices
    # =====================================================
    op.create_table(
        "sensor_devices",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("device_name", sa.String(length=128), nullable=False),
        sa.Column("device_type", sa.String(length=64), nullable=False),
        sa.Column("mqtt_topic", sa.String(length=256), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_sensor_devices_project_id_projects"
        ),
    )
    op.create_index("ix_sensor_devices_tenant_id", "sensor_devices", ["tenant_id"])
    op.create_index("ix_sensor_devices_project_id", "sensor_devices", ["project_id"])

    # =====================================================
    # regulations（5b.3 新增）
    # =====================================================
    op.create_table(
        "regulations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("chapter", sa.String(length=128), nullable=True),
        sa.Column("article", sa.String(length=128), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("related_regulations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "code", "version", "article",
            name="uq_regulation_tenant_code_version_article",
        ),
    )
    op.create_index("ix_regulations_tenant_id", "regulations", ["tenant_id"])
    op.create_index("ix_regulations_code", "regulations", ["code"])

    # =====================================================
    # standards（5b.3 新增）
    # =====================================================
    op.create_table(
        "standards",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "code", "version", name="uq_standard_tenant_code_version"
        ),
    )
    op.create_index("ix_standards_tenant_id", "standards", ["tenant_id"])
    op.create_index("ix_standards_code", "standards", ["code"])

    # =====================================================
    # cases（5b.3 新增）
    # =====================================================
    op.create_table(
        "cases",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("case_no", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("judgment", sa.Text(), nullable=False),
        sa.Column("related_regulations", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "case_no", name="uq_case_tenant_no"),
    )
    op.create_index("ix_cases_tenant_id", "cases", ["tenant_id"])
    op.create_index("ix_cases_case_no", "cases", ["case_no"])

    # =====================================================
    # geofences（5b.3 新增）
    # =====================================================
    op.create_table(
        "geofences",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "fence_type",
            sa.Enum("polygon", "circle", "rect", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("manual", "geojson", "auto", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("center_lon", sa.Float(), nullable=True),
        sa.Column("center_lat", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_geofences_project_id_projects"
        ),
    )
    op.create_index("ix_geofences_tenant_id", "geofences", ["tenant_id"])
    op.create_index("ix_geofences_project_id", "geofences", ["project_id"])

    # =====================================================
    # geofence_violations（5b.3 新增）
    # =====================================================
    op.create_table(
        "geofence_violations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("geofence_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("location", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open", "rectifying", "closed", "waived",
                native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["geofence_id"], ["geofences.id"], name="fk_geofence_violations_geofence_id_geofences"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_geofence_violations_project_id_projects"
        ),
    )
    op.create_index("ix_geofence_violations_tenant_id", "geofence_violations", ["tenant_id"])
    op.create_index("ix_geofence_violations_geofence_id", "geofence_violations", ["geofence_id"])
    op.create_index("ix_geofence_violations_project_id", "geofence_violations", ["project_id"])
    op.create_index("ix_geofence_violations_device_id", "geofence_violations", ["device_id"])
    op.create_index("ix_geofence_violations_occurred_at", "geofence_violations", ["occurred_at"])


def downgrade() -> None:
    # 反序删除
    op.drop_table("geofence_violations")
    op.drop_table("geofences")
    op.drop_table("cases")
    op.drop_table("standards")
    op.drop_table("regulations")
    op.drop_table("sensor_devices")
    op.drop_table("alerts")
    op.drop_table("review_reports")
    op.drop_table("violations")
    op.drop_table("inspections")
    op.drop_table("construction_plans")
    op.drop_table("projects")
    op.drop_table("tenants")
