"""统一异常定义：所有业务异常继承 AppException。

设计要点：
- 异常携带 ErrorCode（错误码 + 默认消息 + HTTP 状态码），API 层统一转响应；
- 各层只抛语义化子类，不直接抛裸 Exception；
- details 用于携带结构化上下文（如失败的模型名、资源 ID），便于排障。
"""

from __future__ import annotations

from typing import Any

from common.error_codes import ErrorCode, ErrorCodes


class AppException(Exception):
    """平台异常基类。"""

    error_code: ErrorCode = ErrorCodes.INTERNAL_ERROR

    def __init__(
        self,
        message: str | None = None,
        *,
        error_code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code or self.error_code
        self.message = message or self.error_code.message
        self.details = details or {}
        super().__init__(self.message)

    @property
    def code(self) -> str:
        return self.error_code.code

    @property
    def http_status(self) -> int:
        return self.error_code.http_status

    def to_dict(self) -> dict[str, Any]:
        """转为 API 统一响应体结构。"""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# ---------- 通用 ----------
class ConfigError(AppException):
    error_code = ErrorCodes.CONFIG_MISSING


class ValidationError(AppException):
    error_code = ErrorCodes.INVALID_PARAMS


class NotFoundError(AppException):
    error_code = ErrorCodes.RESOURCE_NOT_FOUND


class ServiceUnavailableError(AppException):
    error_code = ErrorCodes.SERVICE_UNAVAILABLE


# ---------- 认证/授权 ----------
class AuthenticationError(AppException):
    error_code = ErrorCodes.UNAUTHORIZED


class AuthorizationError(AppException):
    error_code = ErrorCodes.FORBIDDEN


# ---------- 多租户 / 计费（6b.1）----------
class QuotaExceededError(AppException):
    """租户配额用尽（API 调用量 / 存储 / 并发），HTTP 429。"""

    error_code = ErrorCodes.QUOTA_EXCEEDED


class TenantConflictError(AppException):
    """租户状态机冲突 / 编码重复，HTTP 409。"""

    error_code = ErrorCodes.TENANT_CONFLICT


class TenantSuspendedError(AppException):
    """租户已停用或注销，拒绝服务，HTTP 403。"""

    error_code = ErrorCodes.TENANT_SUSPENDED


# ---------- LLM ----------
class LLMError(AppException):
    """LLM 调用失败基类（重试耗尽后抛出）。"""

    error_code = ErrorCodes.LLM_PROVIDER_ERROR


class LLMNotConfiguredError(AppException):
    error_code = ErrorCodes.LLM_NOT_CONFIGURED


class LLMTimeoutError(LLMError):
    error_code = ErrorCodes.LLM_TIMEOUT


class LLMRateLimitError(LLMError):
    error_code = ErrorCodes.LLM_RATE_LIMITED


class LLMResponseInvalidError(LLMError):
    error_code = ErrorCodes.LLM_RESPONSE_INVALID


class LLMAllProvidersFailedError(LLMError):
    error_code = ErrorCodes.LLM_ALL_PROVIDERS_FAILED


# ---------- A2A / MCP ----------
class A2AError(AppException):
    error_code = ErrorCodes.A2A_CALL_FAILED


class A2AMessageInvalidError(A2AError):
    error_code = ErrorCodes.A2A_MESSAGE_INVALID


class A2AAgentNotFoundError(A2AError):
    error_code = ErrorCodes.A2A_AGENT_NOT_FOUND


class A2AProtocolVersionMismatchError(A2AError):
    error_code = ErrorCodes.A2A_PROTOCOL_VERSION_MISMATCH


class A2ATaskNotFoundError(A2AError):
    error_code = ErrorCodes.A2A_TASK_NOT_FOUND


class A2ATimeoutError(A2AError):
    error_code = ErrorCodes.A2A_TIMEOUT


class A2ANetworkError(A2AError):
    error_code = ErrorCodes.A2A_NETWORK_ERROR


class MCPError(AppException):
    error_code = ErrorCodes.MCP_TOOL_EXECUTION_FAILED


class MCPResourceNotFoundError(MCPError):
    error_code = ErrorCodes.MCP_RESOURCE_NOT_FOUND


class MCPToolNotFoundError(MCPError):
    error_code = ErrorCodes.MCP_TOOL_NOT_FOUND


class MCPToolExecutionError(MCPError):
    error_code = ErrorCodes.MCP_TOOL_EXECUTION_FAILED


class MCPProtocolVersionMismatchError(MCPError):
    error_code = ErrorCodes.MCP_PROTOCOL_VERSION_MISMATCH


class MCPPromptNotFoundError(MCPError):
    error_code = ErrorCodes.MCP_PROMPT_NOT_FOUND


# ---------- 事件总线 ----------
class EventPublishError(AppException):
    error_code = ErrorCodes.EVENT_PUBLISH_FAILED


class EventSubscribeError(AppException):
    error_code = ErrorCodes.EVENT_SUBSCRIBE_FAILED


# ---------- 智能体业务 ----------
class AgentError(AppException):
    """智能体业务执行失败基类。"""

    error_code = ErrorCodes.AGENT_CALCULATION_FAILED


class AgentParseError(AppException):
    error_code = ErrorCodes.AGENT_PARSE_FAILED


class RegulationVersionMissingError(AppException):
    """结论未绑定法规版本，违反合规可追溯约束。"""

    error_code = ErrorCodes.AGENT_REGULATION_VERSION_MISSING


# ---------- 任务 ----------
class TaskError(AppException):
    error_code = ErrorCodes.TASK_NOT_FOUND


class TaskStateConflictError(AppException):
    error_code = ErrorCodes.TASK_ALREADY_FINISHED


# ---------- 存储 ----------
class StorageError(AppException):
    error_code = ErrorCodes.STORAGE_WRITE_FAILED


class StorageReadError(AppException):
    error_code = ErrorCodes.STORAGE_READ_FAILED
