"""项目领域模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from common.constants import ProjectStatus
from common.ids import project_id
from common.timeutils import utc_now


class Project(BaseModel):
    """工程项目（数据隔离粒度：tenant_id + id）。"""

    id: str = Field(default_factory=project_id, description="项目 ID (prj_ 前缀)")
    tenant_id: str = Field(description="所属租户 ID")
    name: str = Field(min_length=1, max_length=256, description="项目名称")
    code: str = Field(min_length=1, max_length=64, description="项目编码（租户内唯一）")
    address: str | None = Field(default=None, max_length=512, description="项目地址")
    longitude: float | None = Field(default=None, ge=-180, le=180, description="中心点经度")
    latitude: float | None = Field(default=None, ge=-90, le=90, description="中心点纬度")
    status: ProjectStatus = Field(default=ProjectStatus.DRAFT)
    description: str | None = Field(default=None, description="项目简介")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
