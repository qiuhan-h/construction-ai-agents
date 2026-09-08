"""A2A 客户端：异步 HTTP 调用对端 A2A 服务。

使用方式：
    from core.a2a.client import A2AClient
    client = A2AClient(base_url="http://10.0.0.10:9101", agent_name="safety_audit_agent")
    result = await client.send_message(message, wait=True)

设计要点：
- httpx.AsyncClient 复用，连接池与超时走 BaseURL；
- 失败分类：网络 → A2ANetworkError；4xx → A2AMessageInvalidError；
            5xx → A2AError(A2A_CALL_FAILED)；超时 → A2ATimeoutError；
- 对端 4xx 中带 50004/50005/50006 等专用码的，映射到具体子类。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from common.exceptions import (
    A2AError,
    A2AMessageInvalidError,
    A2ANetworkError,
    A2AProtocolVersionMismatchError,
    A2ATaskNotFoundError,
    A2ATimeoutError,
)
from common.ids import message_id
from common.timeutils import to_iso, utc_now
from core.a2a.message import A2AMessage
from core.a2a.protocol import PROTOCOL_VERSION
from core.a2a.serializers import JSONRPCRequest, decode_request, encode_request

logger = logging.getLogger("core.a2a.client")


class A2AClient:
    """A2A 客户端（单目标 agent 绑定）。"""

    def __init__(
        self,
        base_url: str,
        agent_name: str,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        protocol_version: str = PROTOCOL_VERSION,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.protocol_version = protocol_version
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "A2AClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---------- 公共方法 ----------
    async def discover(self) -> dict[str, Any]:
        """获取对端 Agent Card（GET /a2a/{agent}/agent.json）。"""
        url = f"{self.base_url}/a2a/{self.agent_name}/agent.json"
        try:
            resp = await self._get(url)
        except A2ANetworkError as e:
            raise A2AError("Agent Card 发现失败") from e
        return resp

    async def send_message(
        self,
        message: A2AMessage,
        *,
        wait: bool = False,
    ) -> dict[str, Any]:
        return await self._call_method(
            "agent.send_message",
            {"message": message.model_dump(), "wait": wait},
        )

    async def get_task(self, task_id: str) -> dict[str, Any]:  # noqa: A002
        return await self._call_method("agent.get_task", {"task_id": task_id})

    async def cancel_task(self, task_id: str, reason: str | None = None) -> dict[str, Any]:  # noqa: A002
        return await self._call_method(
            "agent.cancel_task", {"task_id": task_id, "reason": reason}
        )

    async def list_tasks(self) -> dict[str, Any]:
        return await self._call_method("agent.list_tasks", {})

    # ---------- 内部 ----------
    async def _call_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/a2a/{self.agent_name}/{method}"
        req = JSONRPCRequest(
            id=message_id(),
            method=method,
            params=params,
            protocol_version=self.protocol_version,
        )
        body = encode_request(req)
        try:
            data = await self._post_with_retry(url, body)
        except A2ATimeoutError:
            raise
        except A2ANetworkError as e:
            raise A2AError(f"A2A 调用网络失败: {method}") from e

        # 解析 JSON-RPC 响应
        if "error" in data and data["error"]:
            self._raise_for_error(data["error"])
        return data.get("result", {})

    async def _post_with_retry(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        client = self._ensure_client()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.post(url, json=body)
            except httpx.TimeoutException as e:
                last_exc = A2ATimeoutError(f"A2A 调用超时: {url}")
                logger.warning("A2A 超时 attempt=%d url=%s", attempt, url)
            except httpx.HTTPError as e:
                last_exc = A2ANetworkError(f"A2A 网络错误: {e!s}")
                logger.warning("A2A 网络错误 attempt=%d url=%s err=%s", attempt, url, e)
            else:
                # 5xx 服务端错误可重试；4xx / 解析错误立即抛（不重试）。
                # _parse_response 自身对 5xx 仍会抛 A2AError，这里在重试预算
                # 内拦截并退避重试，最后一次尝试交给 _parse_response 抛带 body 的错误。
                if resp.status_code >= 500 and attempt < self.max_retries:
                    last_exc = A2AError(
                        f"A2A 5xx: {resp.status_code}",
                        details={"status": resp.status_code},
                    )
                    logger.warning(
                        "A2A 5xx attempt=%d url=%s status=%s → 重试",
                        attempt, url, resp.status_code,
                    )
                else:
                    return self._parse_response(resp)

            # 退避
            if attempt < self.max_retries:
                await asyncio.sleep(self.backoff_seconds * (attempt + 1))

        assert last_exc is not None
        raise last_exc

    async def _get(self, url: str) -> dict[str, Any]:
        client = self._ensure_client()
        try:
            resp = await client.get(url)
        except httpx.TimeoutException as e:
            raise A2ATimeoutError(f"A2A GET 超时: {url}") from e
        except httpx.HTTPError as e:
            raise A2ANetworkError(f"A2A GET 网络错误: {e!s}") from e
        return self._parse_response(resp)

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
            self._owns_client = True
        return self._client

    def _parse_response(self, resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except Exception as e:
            raise A2AMessageInvalidError(
                f"A2A 响应非 JSON: status={resp.status_code}",
                details={"status": resp.status_code, "text": resp.text[:200]},
            ) from e
        if resp.status_code >= 500:
            raise A2AError(
                f"A2A 5xx: {resp.status_code}",
                details={"body": data},
            )
        if resp.status_code >= 400:
            # 4xx 立即抛错，不重试
            err = data.get("error") if isinstance(data, dict) else None
            if err:
                self._raise_for_error(err)
            raise A2AMessageInvalidError(
                f"A2A 4xx: {resp.status_code}",
                details={"status": resp.status_code, "body": data},
            )
        return data if isinstance(data, dict) else {"result": data}

    def _raise_for_error(self, err: dict[str, Any]) -> None:
        code = str(err.get("code", ""))
        message = err.get("message", "A2A 错误")
        data = err.get("data") or {}
        if code == "50004":
            raise A2AProtocolVersionMismatchError(message, details=data)
        if code == "50005":
            raise A2ATaskNotFoundError(message, details=data)
        if code == "50006":
            raise A2ATimeoutError(message, details=data)
        if code == "50007":
            raise A2ANetworkError(message, details=data)
        if code == "50002":
            raise A2AMessageInvalidError(message, details=data)
        if code == "50001":
            from common.exceptions import A2AAgentNotFoundError
            raise A2AAgentNotFoundError(message, details=data)
        # 兜底
        raise A2AError(message, details={**data, "code": code})


# =====================================================
# 便捷工厂
# =====================================================
def build_message(tenant_id: str, text: str, *, role: str = "user",
                  metadata: dict[str, Any] | None = None) -> A2AMessage:
    """快速构造一条用户消息。"""
    from core.a2a.message import MessagePart
    return A2AMessage(
        message_id=message_id(),
        tenant_id=tenant_id,
        role=role,
        parts=[MessagePart(type="text", text=text)],
        metadata=metadata or {},
        created_at=to_iso(utc_now()),
    )
