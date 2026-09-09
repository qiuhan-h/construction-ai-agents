"""MCP 资源：法规 / 标准 / 案例。"""

from core.mcp.resources.case_resource import (  # noqa: F401
    CASE_URI_PREFIX,
    list_cases,
    read_case,
)
from core.mcp.resources.regulation_resource import (  # noqa: F401
    REGULATION_URI_PREFIX,
    list_regulations,
    read_regulation,
)
from core.mcp.resources.standard_resource import (  # noqa: F401
    STANDARD_URI_PREFIX,
    list_standards,
    read_standard,
)
