"""BIM 集成子包：BIM API + IFC 解析 + 进度跟踪。

5b.5 起：
- ``BIMConnector``         — 4c mock 客户端（兼容保留）
- ``BIMRealConnector``     — 5b.5 真实 APS / BIM360 客户端（缺凭据降级）
- ``IFCParser``             — 4c mock 解析器
- ``IFCRealParser``        — 5b.5 真实 ifcopenshell 解析器
- ``ProgressItem`` / ``ProgressTracker`` — 进度对比 + 偏差告警
"""

from agents.site_monitor_agent.bim_integration.bim_connector import (
    BIMConnector,
)
from agents.site_monitor_agent.bim_integration.bim_real_connector import (
    BIMRealConnector,
    make_bim_real_connector,
)
from agents.site_monitor_agent.bim_integration.ifc_parser import IFCParser
from agents.site_monitor_agent.bim_integration.ifc_real_parser import IFCRealParser
from agents.site_monitor_agent.bim_integration.progress_tracker import (
    ProgressItem,
    ProgressTracker,
)

__all__ = [
    "BIMConnector",
    "BIMRealConnector",
    "IFCParser",
    "IFCRealParser",
    "ProgressItem",
    "ProgressTracker",
    "make_bim_real_connector",
]
