"""事件类型定义：跨智能体异步协作的消息载体。

设计要点：
- 业务事件用 dataclass（不可变），便于通过 JSON 序列化跨进程传输；
- 每个事件必带 event_id（evt_ 前缀）、tenant_id、occurred_at；
- topic 字段采用 "<domain>.<action>" 形式（如 "inspection.completed"），
  订阅端可使用通配符 "inspection.*" 匹配一类事件。

注意：
- 事件 payload 不直接承载大文件 / 大块文本；如需引用，请用资源 URI
  （MCP regulation://、case://、standard:// 等）。
- 多租户隔离：所有事件必带 tenant_id，订阅 handler 入口应再做一次校验。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from common.timeutils import to_iso, utc_now
from common.ids import event_id


# =====================================================
# 主题常量（供订阅端 / 业务端统一引用）
# =====================================================
TOPIC_INSPECTION_COMPLETED = "inspection.completed"     # 一次审查/巡检完成
TOPIC_VIOLATION_CREATED = "violation.created"            # 新增违规项
TOPIC_VIOLATION_RECTIFIED = "violation.rectified"        # 违规项已整改
TOPIC_ALERT_TRIGGERED = "alert.triggered"                # 现场告警触发
TOPIC_ALERT_RESOLVED = "alert.resolved"                  # 告警处置完成
TOPIC_REPORT_SIGNED = "report.signed"                    # 报告已签章
TOPIC_AGENT_TASK_DONE = "agent.task.done"                # 智能体异步任务完成
TOPIC_REGULATION_UPDATED = "regulation.updated"          # 法规库更新（版本变更）


# 所有可订阅主题（用于运行时校验）
KNOWN_TOPICS: tuple[str, ...] = (
    TOPIC_INSPECTION_COMPLETED,
    TOPIC_VIOLATION_CREATED,
    TOPIC_VIOLATION_RECTIFIED,
    TOPIC_ALERT_TRIGGERED,
    TOPIC_ALERT_RESOLVED,
    TOPIC_REPORT_SIGNED,
    TOPIC_AGENT_TASK_DONE,
    TOPIC_REGULATION_UPDATED,
)


# =====================================================
# 事件基类与具体事件
# =====================================================
@dataclass(frozen=True)
class Event:
    """事件基类（不可变）。

    Attributes:
        topic: 事件主题（领域.动作）
        tenant_id: 多租户隔离
        source: 事件来源（智能体名 / 服务名）
        payload: 事件载荷（业务相关字段）
        event_id: 事件唯一 ID（evt_ 前缀，由 common.ids.event_id 生成）
        occurred_at: 事件发生时间（ISO-8601，UTC）
        metadata: 自由扩展字段（trace_id、correlation_id 等）

    设计说明：
        所有字段均有默认值，使子类可以仅覆盖 topic 字段。
        业务调用应使用 Event.of(...) 或 publish(...) 工厂，传入必填项。
    """

    topic: str = ""
    tenant_id: str = ""
    source: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=event_id)
    occurred_at: str = field(default_factory=lambda: to_iso(utc_now()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def of(
        cls,
        topic: str,
        tenant_id: str,
        source: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Event":
        return cls(
            topic=topic,
            tenant_id=tenant_id,
            source=source,
            payload=payload or {},
            metadata=metadata or {},
        )


# ---------- 业务事件（语义化子类，方便订阅端 isinstance 过滤） ----------
@dataclass(frozen=True)
class InspectionCompletedEvent(Event):
    """审查/巡检完成事件。"""

    topic: str = TOPIC_INSPECTION_COMPLETED


@dataclass(frozen=True)
class ViolationCreatedEvent(Event):
    """新增违规项事件。"""

    topic: str = TOPIC_VIOLATION_CREATED


@dataclass(frozen=True)
class ViolationRectifiedEvent(Event):
    """违规项已整改事件。"""

    topic: str = TOPIC_VIOLATION_RECTIFIED


@dataclass(frozen=True)
class AlertTriggeredEvent(Event):
    """告警触发事件。"""

    topic: str = TOPIC_ALERT_TRIGGERED


@dataclass(frozen=True)
class AlertResolvedEvent(Event):
    """告警已处置事件。"""

    topic: str = TOPIC_ALERT_RESOLVED


@dataclass(frozen=True)
class ReportSignedEvent(Event):
    """审查报告已签章事件。"""

    topic: str = TOPIC_REPORT_SIGNED


@dataclass(frozen=True)
class AgentTaskDoneEvent(Event):
    """智能体异步任务完成事件。"""

    topic: str = TOPIC_AGENT_TASK_DONE


@dataclass(frozen=True)
class RegulationUpdatedEvent(Event):
    """法规库更新事件（版本变更，可触发下游重算/重审）。"""

    topic: str = TOPIC_REGULATION_UPDATED
