"""API 层统一响应结构。

设计要点：
- 所有 API 接口统一返回 ApiResponse[T] 形式，简化前端处理；
- code / message / data 三段式；
- code 字段为字符串，承载业务错误码（与 common.error_codes 配合）；
- 分页响应使用 Page[T]（pagination.py）；
- 当 data 为 None 且 request_id 存在时，自动填充 request_id，便于链路追踪。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# =====================================================
# 统一响应包装
# =====================================================
class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应。

    示例：
        ApiResponse[dict](code="0", message="ok", data={"id": "prj_..."})
        ApiResponse[str].ok("hi")
        ApiResponse[Any].fail("50002", "bad", details={"x": 1})
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(default="0", description="业务状态码：0 表示成功，其它见 common.error_codes")
    message: str = Field(default="ok", description="人类可读消息")
    # 故意使用 Any：失败响应的 data 承载 details dict，类型不固定。
    data: Any | None = Field(default=None, description="业务数据，类型由泛型决定")
    request_id: str | None = Field(default=None, description="请求 ID（用于链路追踪）")
    timestamp: str | None = Field(default=None, description="响应时间（ISO-8601 UTC）")

    @classmethod
    def ok(
        cls,
        data: T | None = None,
        *,
        message: str = "ok",
        request_id: str | None = None,
    ) -> "ApiResponse[T]":
        from common.timeutils import to_iso, utc_now

        return cls(
            code="0",
            message=message,
            data=data,
            request_id=request_id,
            timestamp=to_iso(utc_now()),
        )

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
        http_status: int | None = None,
    ) -> "ApiResponse[T]":
        from common.timeutils import to_iso, utc_now

        data: Any = None
        if details:
            data = {"details": details}
        return cls(
            code=code,
            message=message,
            data=data,  # type: ignore[assignment]
            request_id=request_id,
            timestamp=to_iso(utc_now()),
        )

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        *,
        request_id: str | None = None,
    ) -> "ApiResponse[Any]":
        """从 AppException 派生响应。"""
        from common.exceptions import AppException
        from common.timeutils import to_iso, utc_now

        if isinstance(exc, AppException):
            return cls(
                code=exc.code,
                message=exc.message,
                data={"details": exc.details} if exc.details else None,
                request_id=request_id,
                timestamp=to_iso(utc_now()),
            )
        return cls(
            code="10001",
            message=str(exc) or "internal error",
            request_id=request_id,
            timestamp=to_iso(utc_now()),
        )


# =====================================================
# 错误响应（更详细的错误体）
# =====================================================
class ErrorDetail(BaseModel):
    """单条错误明细（用于表单/参数级校验错误）。"""

    model_config = ConfigDict(extra="forbid")

    field: str | None = Field(default=None, description="出错字段（点路径）")
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误描述")
    hint: str | None = Field(default=None, description="修复建议")


class ErrorResponse(BaseModel):
    """API 错误响应体（用于 4xx/5xx 响应）。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="业务错误码")
    message: str = Field(..., description="人类可读错误描述")
    errors: list[ErrorDetail] = Field(
        default_factory=list,
        description="逐项错误（参数校验失败时填充）",
    )
    request_id: str | None = Field(default=None)
    timestamp: str = Field(default_factory=lambda: _now_iso())


def _now_iso() -> str:
    from common.timeutils import to_iso, utc_now
    return to_iso(utc_now())


__all__ = [
    "ApiResponse",
    "ErrorDetail",
    "ErrorResponse",
]
