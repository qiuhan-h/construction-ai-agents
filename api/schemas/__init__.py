"""api.schemas 公共 API。"""

from api.schemas.bim_schemas import (
    BIMElement,
    BIMProgressItem,
    BIMProgressResponse,
    BIMProjectTreeNode,
)
from api.schemas.a2a_schemas import (
    A2ACancelTaskRequest,
    A2ACancelTaskResponse,
    A2AErrorInfo,
    A2AErrorResponse,
    A2AGetTaskResponse,
    A2AListTasksResponse,
    A2AMessageDTO,
    A2AMessagePartDTO,
    A2ASendMessageRequest,
    A2ASendMessageResponse,
)
from api.schemas.agent_schemas import (
    AgentCapabilitiesDTO,
    AgentCardDTO,
    AgentDetail,
    AgentHealthResponse,
    AgentListResponse,
    AgentSkillDTO,
    AgentSummary,
)
from api.schemas.mobile_schemas import (
    MobileAlertListItem,
    MobileDashboard,
    MobileProjectCard,
)
from api.schemas.pagination import Page, PaginationQuery
from api.schemas.response_schemas import ApiResponse, ErrorDetail, ErrorResponse

__all__ = [
    # 响应
    "ApiResponse",
    "ErrorDetail",
    "ErrorResponse",
    # 分页
    "Page",
    "PaginationQuery",
    # A2A DTO
    "A2AMessagePartDTO",
    "A2AMessageDTO",
    "A2ASendMessageRequest",
    "A2ASendMessageResponse",
    "A2AGetTaskResponse",
    "A2ACancelTaskRequest",
    "A2ACancelTaskResponse",
    "A2AListTasksResponse",
    "A2AErrorInfo",
    "A2AErrorResponse",
    # 智能体 DTO
    "AgentSkillDTO",
    "AgentCapabilitiesDTO",
    "AgentCardDTO",
    "AgentSummary",
    "AgentDetail",
    "AgentListResponse",
    "AgentHealthResponse",
    # 移动端
    "MobileAlertListItem",
    "MobileDashboard",
    "MobileProjectCard",
    # BIM
    "BIMElement",
    "BIMProjectTreeNode",
    "BIMProgressItem",
    "BIMProgressResponse",
]
