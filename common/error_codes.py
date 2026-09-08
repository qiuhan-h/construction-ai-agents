"""统一错误码定义。

编码规则：5 位数字，首位为模块域
    1xxx 通用      2xxx 配置        3xxx 认证/授权
    4xxx LLM       5xxx A2A        6xxx MCP
    7xxx 智能体业务 8xxx 任务        9xxx 存储

每个错误码携带：默认消息 + 对应 HTTP 状态码（API 层直接映射响应）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    code: str
    message: str
    http_status: int


class ErrorCodes:
    # ---------- 通用 1xxx ----------
    INTERNAL_ERROR = ErrorCode("10001", "服务器内部错误", 500)
    INVALID_PARAMS = ErrorCode("10002", "请求参数无效", 400)
    RESOURCE_NOT_FOUND = ErrorCode("10003", "资源不存在", 404)
    METHOD_NOT_ALLOWED = ErrorCode("10004", "请求方法不允许", 405)
    SERVICE_UNAVAILABLE = ErrorCode("10005", "服务暂不可用", 503)
    TIMEOUT = ErrorCode("10006", "操作超时", 504)

    # ---------- 配置 2xxx ----------
    CONFIG_MISSING = ErrorCode("20001", "缺少必要配置项", 500)
    CONFIG_INVALID = ErrorCode("20002", "配置项格式错误", 500)

    # ---------- 认证/授权/租户 3xxx ----------
    UNAUTHORIZED = ErrorCode("30001", "未认证或认证已过期", 401)
    FORBIDDEN = ErrorCode("30002", "无权限执行该操作", 403)
    TENANT_SUSPENDED = ErrorCode("30003", "租户已停用", 403)
    # 6b.1 多租户 SaaS：配额限流 / 租户状态冲突
    QUOTA_EXCEEDED = ErrorCode("30004", "租户配额已用尽，请升级套餐", 429)
    TENANT_CONFLICT = ErrorCode("30005", "租户状态冲突或编码重复", 409)

    # ---------- LLM 4xxx ----------
    LLM_NOT_CONFIGURED = ErrorCode("40001", "LLM 未配置（缺少 API Key）", 500)
    LLM_TIMEOUT = ErrorCode("40002", "LLM 请求超时", 504)
    LLM_RATE_LIMITED = ErrorCode("40003", "LLM 触发限流", 429)
    LLM_PROVIDER_ERROR = ErrorCode("40004", "LLM 服务提供方错误", 502)
    LLM_RESPONSE_INVALID = ErrorCode("40005", "LLM 返回内容格式异常", 502)
    LLM_ALL_PROVIDERS_FAILED = ErrorCode("40006", "所有候选模型均调用失败", 502)

    # ---------- A2A 5xxx ----------
    A2A_AGENT_NOT_FOUND = ErrorCode("50001", "目标智能体未注册", 404)
    A2A_MESSAGE_INVALID = ErrorCode("50002", "A2A 消息结构无效", 400)
    A2A_CALL_FAILED = ErrorCode("50003", "A2A 调用失败", 502)
    A2A_PROTOCOL_VERSION_MISMATCH = ErrorCode("50004", "A2A 协议版本不兼容", 400)
    A2A_TASK_NOT_FOUND = ErrorCode("50005", "A2A 任务不存在", 404)
    A2A_TIMEOUT = ErrorCode("50006", "A2A 调用超时", 504)
    A2A_NETWORK_ERROR = ErrorCode("50007", "A2A 网络错误", 502)

    # ---------- MCP 6xxx ----------
    MCP_RESOURCE_NOT_FOUND = ErrorCode("60001", "MCP 资源不存在", 404)
    MCP_TOOL_NOT_FOUND = ErrorCode("60002", "MCP 工具不存在", 404)
    MCP_TOOL_EXECUTION_FAILED = ErrorCode("60003", "MCP 工具执行失败", 500)
    MCP_PROTOCOL_VERSION_MISMATCH = ErrorCode("60004", "MCP 协议版本不兼容", 400)
    MCP_PROMPT_NOT_FOUND = ErrorCode("60005", "MCP 提示词模板不存在", 404)

    # ---------- 智能体业务 7xxx ----------
    AGENT_PARSE_FAILED = ErrorCode("70001", "文档解析失败", 422)
    AGENT_CALCULATION_FAILED = ErrorCode("70002", "计算执行失败", 500)
    AGENT_REGULATION_VERSION_MISSING = ErrorCode(
        "70003", "结论缺少法规版本绑定（合规可追溯要求）", 500
    )
    AGENT_REVIEW_REQUIRED = ErrorCode("70004", "任务进入人工复核队列", 202)

    # ---------- 任务 8xxx ----------
    TASK_NOT_FOUND = ErrorCode("80001", "任务不存在", 404)
    TASK_ALREADY_FINISHED = ErrorCode("80002", "任务已结束，不可重复操作", 409)
    TASK_QUEUE_FULL = ErrorCode("80003", "任务队列已满，请稍后重试", 429)
    # ---------- 事件总线 8xxx ----------
    EVENT_PUBLISH_FAILED = ErrorCode("80004", "事件发布失败", 502)
    EVENT_SUBSCRIBE_FAILED = ErrorCode("80005", "事件订阅失败", 500)

    # ---------- 存储 9xxx ----------
    STORAGE_READ_FAILED = ErrorCode("90001", "文件读取失败", 500)
    STORAGE_WRITE_FAILED = ErrorCode("90002", "文件写入失败", 500)
    STORAGE_UPLOAD_REJECTED = ErrorCode("90003", "上传文件被拒绝", 415)
