"""MCP 资源：法规 / 标准 / 案例。"""

from core.mcp.resources.case_resource import (  # noqa: F401
    read_case,
    list_cases,
    CASE_URI_PREFIX,
)
from core.mcp.resources.regulation_resource import (  # noqa: F401
    read_regulation,
    list_regulations,
    REGULATION_URI_PREFIX,
)
from core.mcp.resources.standard_resource import (  # noqa: F401
    read_standard,
    list_standards,
    STANDARD_URI_PREFIX,
)
