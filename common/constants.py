"""常量与枚举：全平台共享的标识、状态、等级定义。

约定：
- 所有跨模块的状态值一律使用本文件的枚举，禁止散落字符串字面量。
- 枚举成员名英文大写，值为短横线/下划线小写（用于存储与 API 传输）。
"""

from __future__ import annotations

from enum import Enum

# ---------- 应用常量 ----------
APP_NAME = "construction-ai-agents"
APP_VERSION = "0.1.0"

# 默认向量集合名（与 config/agent_configs.yaml 对齐）
DEFAULT_CASE_COLLECTION = "construction_cases"


class AgentName(str, Enum):
    """平台内智能体标识（与 config/a2a_config.yaml 的 registry 一一对应）。"""

    ORCHESTRATOR = "orchestrator"
    SAFETY_AUDIT = "safety_audit_agent"
    COMPLIANCE = "compliance_agent"
    SITE_MONITOR = "site_monitor_agent"

    @property
    def is_business(self) -> bool:
        """业务智能体（执行具体审查/监控）与协调者的区分。"""
        return self is not AgentName.ORCHESTRATOR


class TenantStatus(str, Enum):
    """租户状态（6b.1 状态机：trial → active → suspended → closed）。"""

    TRIAL = "trial"          # 试用（30 天 + 100 次调用额度）
    ACTIVE = "active"        # 已订阅付费套餐
    SUSPENDED = "suspended"  # 停用（欠费 / 违规）
    CLOSED = "closed"        # 注销（终态）


class SubscriptionPlan(str, Enum):
    """租户订阅套餐（6b.1 计费/配额）。

    - trial      试用：30 天，100 次 API 调用，1GB 存储，1 并发
    - starter    入门版：10,000 次/月，10GB，3 并发
    - pro        专业版：100,000 次/月，100GB，10 并发
    - enterprise 企业版：不限调用量，1000GB，50 并发
    """

    TRIAL = "trial"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class ProjectStatus(str, Enum):
    """项目状态。"""

    DRAFT = "draft"
    DESIGN = "design"
    CONSTRUCTION = "construction"
    COMPLETED = "completed"
    SUSPENDED = "suspended"


class PlanType(str, Enum):
    """施工方案类型（安全审核的主要对象）。"""

    SCAFFOLDING = "scaffolding"            # 脚手架工程
    FORMWORK = "formwork"                  # 模板工程
    DEEP_FOUNDATION_PIT = "deep_foundation_pit"  # 深基坑
    HOISTING = "hoisting"                  # 起重吊装
    TEMP_ELECTRICAL = "temp_electrical"    # 临时用电
    DEMOLITION = "demolition"              # 拆除工程
    OTHER = "other"


class PlanStatus(str, Enum):
    """施工方案状态。"""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class InspectionStatus(str, Enum):
    """审查/检查任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditConclusion(str, Enum):
    """审查结论。"""

    PASS = "pass"                          # 通过
    CONDITIONAL_PASS = "conditional_pass"  # 有条件通过（需整改后复查）
    FAIL = "fail"                          # 不通过


class ViolationSeverity(str, Enum):
    """违规项严重程度。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ViolationStatus(str, Enum):
    """违规项整改状态。"""

    OPEN = "open"                # 待整改
    RECTIFYING = "rectifying"    # 整改中
    CLOSED = "closed"            # 已闭环
    WAIVED = "waived"            # 经人工复核豁免


class AlertLevel(str, Enum):
    """告警等级。"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """告警处置状态。"""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ReportStatus(str, Enum):
    """审查报告状态（SIGNED 表示已经 report_signer 签章）。"""

    DRAFT = "draft"
    SIGNED = "signed"
    FINAL = "final"


class TaskStatus(str, Enum):
    """异步任务（Celery）状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class ResourceType(str, Enum):
    """MCP 资源类型（法规/标准/案例）。"""

    REGULATION = "regulation"
    STANDARD = "standard"
    CASE = "case"


class DocType(str, Enum):
    """向量库中文档类型。"""

    REGULATION = "regulation"
    STANDARD = "standard"
    CASE = "case"
    PLAN = "plan"


# ---------- 阶段五新增（5b.3 / 5b.7）----------
class GeofenceType(str, Enum):
    """地理围栏几何类型。"""

    POLYGON = "polygon"          # 多边形（首版默认）
    CIRCLE = "circle"            # 圆形
    RECT = "rect"                # 矩形


class FenceSource(str, Enum):
    """围栏数据来源。"""

    MANUAL = "manual"            # 人工录入
    GEOJSON = "geojson"          # GeoJSON 导入
    AUTO = "auto"                # 系统自动生成
