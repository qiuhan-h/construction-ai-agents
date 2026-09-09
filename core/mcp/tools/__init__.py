"""MCP 工具：计算 / 校验 / 分析。

首版实现为结构化空壳 + 占位算法；阶段三/四在 safety_audit_agent 等
calculators 目录中替换为真实算法（GB50009/GB50011 等）。
"""

from core.mcp.tools.analysis_tools import (  # noqa: F401
    aggregate_risk,
    summarize_violations,
)
from core.mcp.tools.calculation_tools import (  # noqa: F401
    assess_risk,
    calculate_load,
    structural_check,
)
from core.mcp.tools.validation_tools import (  # noqa: F401
    validate_document,
    validate_drawing,
    validate_plan,
)
