"""services 包级 re-export。

公开 API：
- TaskQueue / get_task_queue           任务队列（Celery + mock 降级）
- celery_app                           Celery 应用（worker 入口）
- HumanReviewService / Repository      人工复核
- DocumentService                      文档服务
- NotificationService / channels       多渠道通知
- DataIngestionService                 IoT / 文件 / API 数据接入
- ServiceRegistry                      system 动作路由
"""

from services.data_ingestion import (
    APIRecord,
    DataIngestionService,
    FileArtifact,
    IngestionRepository,
    SensorPoint,
    get_data_ingestion_service,
    reset_data_ingestion_service,
)
from services.document_service import (
    DocumentMeta,
    DocumentService,
    get_document_service,
    reset_document_service,
)
from services.human_review_repository import (
    HumanReviewRepository,
    HumanReviewRow,
)
from services.human_review_service import (
    HumanReviewService,
    get_human_review_service,
    reset_human_review_service,
)
from services.notification_service import (
    NotificationService,
    get_notification_service,
    reset_notification_service,
)
from services.service_registry import (
    ServiceRegistry,
    get_service,
    is_registered,
    list_services,
    register_service,
    unregister_service,
)
from services.task_queue import (
    TaskQueue,
    get_task_queue,
    reset_task_queue,
)

__all__ = [
    # 队列 / 调度
    "TaskQueue",
    "get_task_queue",
    "reset_task_queue",
    # 人工复核
    "HumanReviewService",
    "HumanReviewRepository",
    "HumanReviewRow",
    "get_human_review_service",
    "reset_human_review_service",
    # 文档
    "DocumentService",
    "DocumentMeta",
    "get_document_service",
    "reset_document_service",
    # 通知
    "NotificationService",
    "get_notification_service",
    "reset_notification_service",
    # 数据接入
    "DataIngestionService",
    "IngestionRepository",
    "SensorPoint",
    "FileArtifact",
    "APIRecord",
    "get_data_ingestion_service",
    "reset_data_ingestion_service",
    # 服务注册表
    "ServiceRegistry",
    "register_service",
    "list_services",
    "get_service",
    "is_registered",
    "unregister_service",
]
