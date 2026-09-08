"""core/orchestrator 包级 re-export。

公开 API：
- Orchestrator：主编排器
- WorkflowEngine / Workflow / TaskSpec：工作流描述与执行
- TaskScheduler：任务调度（Celery 入队）
- CollaborationManager：多智能体协作时间线
- HumanReviewServiceAdapter：人机交互适配
- AgentManagerProtocol：4c 协议，4d 实现
"""

from core.orchestrator.collaboration_manager import (
    CollaborationEntry,
    CollaborationManager,
)
from core.orchestrator.human_interaction import (
    HumanReviewServiceAdapter,
    get_human_review_adapter,
    reset_human_review_adapter,
)
from core.orchestrator.orchestrator import Orchestrator
from core.orchestrator.task_scheduler import (
    MAX_RETRIES,
    TaskScheduler,
    TaskSchedulerError,
    register_celery_tasks,
)
from core.orchestrator.workflow_engine import (
    AgentManagerProtocol,
    TaskSpec,
    Workflow,
    WorkflowEngine,
)

__all__ = [
    # 主编排
    "Orchestrator",
    # 工作流
    "WorkflowEngine",
    "Workflow",
    "TaskSpec",
    "AgentManagerProtocol",
    # 调度
    "TaskScheduler",
    "TaskSchedulerError",
    "MAX_RETRIES",
    "register_celery_tasks",
    # 协作
    "CollaborationManager",
    "CollaborationEntry",
    # 人机交互
    "HumanReviewServiceAdapter",
    "get_human_review_adapter",
    "reset_human_review_adapter",
]
