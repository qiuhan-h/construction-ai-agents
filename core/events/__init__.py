"""core.events 公共 API。

公开导出：
- 事件类型：Event 及业务事件子类
- 主题常量：TOPIC_*  系列
- 事件总线：EventBus, get_event_bus, reset_event_bus
- 便捷发布：publish, publish_sync
"""

from core.events.event_bus import (
    EventBus,
    EventHandler,
    get_event_bus,
    publish,
    publish_sync,
    reset_event_bus,
)
from core.events.events import (
    KNOWN_TOPICS,
    AgentTaskDoneEvent,
    AlertResolvedEvent,
    AlertTriggeredEvent,
    Event,
    InspectionCompletedEvent,
    RegulationUpdatedEvent,
    ReportSignedEvent,
    TOPIC_AGENT_TASK_DONE,
    TOPIC_ALERT_RESOLVED,
    TOPIC_ALERT_TRIGGERED,
    TOPIC_INSPECTION_COMPLETED,
    TOPIC_REGULATION_UPDATED,
    TOPIC_REPORT_SIGNED,
    TOPIC_VIOLATION_CREATED,
    TOPIC_VIOLATION_RECTIFIED,
    ViolationCreatedEvent,
    ViolationRectifiedEvent,
)

__all__ = [
    # 事件总线
    "EventBus",
    "EventHandler",
    "get_event_bus",
    "reset_event_bus",
    "publish",
    "publish_sync",
    # 事件
    "Event",
    "InspectionCompletedEvent",
    "ViolationCreatedEvent",
    "ViolationRectifiedEvent",
    "AlertTriggeredEvent",
    "AlertResolvedEvent",
    "ReportSignedEvent",
    "AgentTaskDoneEvent",
    "RegulationUpdatedEvent",
    # 主题
    "KNOWN_TOPICS",
    "TOPIC_INSPECTION_COMPLETED",
    "TOPIC_VIOLATION_CREATED",
    "TOPIC_VIOLATION_RECTIFIED",
    "TOPIC_ALERT_TRIGGERED",
    "TOPIC_ALERT_RESOLVED",
    "TOPIC_REPORT_SIGNED",
    "TOPIC_AGENT_TASK_DONE",
    "TOPIC_REGULATION_UPDATED",
]
