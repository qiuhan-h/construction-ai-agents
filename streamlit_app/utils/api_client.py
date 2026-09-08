"""同步 HTTP 客户端（Streamlit 友好）。

约定：
- 默认 base_url 从 settings.api_base_url 读（或环境变量 API_BASE_URL）；
- 默认 Authorization 走 dev- 前缀 token，格式：dev-{tenant_id}-{user_id}；
- 响应统一走 ApiResponse 形状（4d 已约定）；失败抛 APIError，message / code 可直接 st.error；
- 不依赖 langchain / orchestrator 内部模块，仅 httpx + os。
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


class APIError(RuntimeError):
    """API 调用失败的统一异常。"""

    def __init__(self, message: str, code: str = "", status: int = 0, data: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.data = data


class APIClient:
    """Streamlit 侧同步 HTTP 客户端。"""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("API_BASE_URL")
            or "http://127.0.0.1:8000"
        ).rstrip("/")
        self.token = token or os.getenv("API_AUTH_TOKEN") or ""
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    # ---------- 配置 ----------
    def configure(self, base_url: str | None = None, token: str | None = None) -> None:
        if base_url:
            self.base_url = base_url.rstrip("/")
        if token is not None:
            self.token = token

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    # ---------- 底层 ----------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        raw: bool = False,
    ) -> Any:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        try:
            resp = self._client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers={**self.auth_headers, "Accept": "application/json"},
            )
        except httpx.RequestError as e:
            raise APIError(f"网络错误: {e}", code="NETWORK", status=0) from e

        # FastAPI HTTPException（路由 raise）→ {"detail": {"code":..., "message":...}}
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                raise APIError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}",
                    code="HTTP",
                    status=resp.status_code,
                )
            detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(detail, dict):
                raise APIError(
                    detail.get("message", "API error"),
                    code=str(detail.get("code", "")),
                    status=resp.status_code,
                    data=detail.get("data"),
                )
            raise APIError(
                str(body)[:200] or f"HTTP {resp.status_code}",
                code=str(resp.status_code),
                status=resp.status_code,
                data=body,
            )

        if raw:
            return resp
        try:
            envelope = resp.json()
        except Exception as e:  # noqa: BLE001
            raise APIError(f"响应不是 JSON: {e}", code="PARSE", status=resp.status_code) from e

        # 统一 ApiResponse 包壳：成功 → data 字段；失败 → 抛错
        if isinstance(envelope, dict) and "code" in envelope:
            if str(envelope.get("code")) == "0":
                return envelope.get("data")
            raise APIError(
                envelope.get("message", "业务错误"),
                code=str(envelope.get("code", "")),
                status=resp.status_code,
                data=envelope.get("data"),
            )
        # 非包壳响应：原样返回
        return envelope

    # ---------- 业务方法 ----------
    def healthz(self) -> dict:
        return self._request("GET", "/api/v1/health/healthz")

    def readyz(self) -> dict:
        return self._request("GET", "/api/v1/health/readyz")

    def list_supported_agents(self) -> list[str]:
        data = self._request("GET", "/api/v1/agents/supported")
        return list((data or {}).get("supported", [])) if isinstance(data, dict) else []

    def get_agent_card(self, name: str) -> dict:
        return self._request("GET", f"/api/v1/agents/{name}/card")

    def list_workflows(self) -> dict:
        return self._request("GET", "/api/v1/orchestrator/workflows")

    def get_workflow(self, name: str) -> dict:
        return self._request("GET", f"/api/v1/orchestrator/workflows/{name}")

    def trigger_workflow(
        self,
        name: str,
        payload: dict | None = None,
        *,
        via_query: bool = False,
    ) -> dict:
        """触发工作流。

        - via_query=False（默认）：payload 作 body JSON；
        - via_query=True：payload 作 ?payload={...}（兼容 4d query 入口）。
        """
        import json as _json

        if via_query:
            return self._request(
                "POST",
                f"/api/v1/orchestrator/workflows/{name}/trigger",
                params={"payload": _json.dumps(payload or {}, ensure_ascii=False)},
            )
        return self._request(
            "POST",
            f"/api/v1/orchestrator/workflows/{name}/trigger",
            json_body=payload or {},
        )

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/api/v1/orchestrator/runs/{run_id}")

    def list_timeline(self, limit: int | None = None) -> dict:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = int(limit)
        return self._request("GET", "/api/v1/orchestrator/timeline", params=params or None)

    def get_stats(self) -> dict:
        return self._request("GET", "/api/v1/orchestrator/stats")

    def list_reports(self, project_id: str | None = None, page: int = 1, page_size: int = 20) -> dict:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if project_id:
            params["project_id"] = project_id
        return self._request("GET", "/api/v1/reports", params=params)

    # ---------- 移动端精简接口（6c.2）----------
    def mobile_dashboard(self) -> dict:
        """移动端首页仪表盘（聚合 KPI + 最近告警 + 项目卡片，< 5KB）。"""
        return self._request("GET", "/api/v1/mobile/dashboard")

    def mobile_alerts(self) -> list:
        """移动端告警列表（≤20 条精简字段）。"""
        return self._request("GET", "/api/v1/mobile/alerts")

    def mobile_projects(self) -> list:
        """移动端项目卡片列表（≤10 个）。"""
        return self._request("GET", "/api/v1/mobile/projects")

    # ---------- 资源释放 ----------
    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass


# 单例（方便页面直接用；仅当 Streamlit 不可用时回退到此全局单例）
_default_client: APIClient | None = None


def api_client() -> APIClient:
    """获取当前会话的 API 客户端。

    - Streamlit 可用：按 ``st.session_state`` 隔离客户端，避免多用户共享
      token 导致的跨租户串户；
    - Streamlit 不可用（CLI / 单元测试 / 无 streamlit 环境）：回退到模块级单例。
    """
    global _default_client
    try:
        import streamlit as st  # type: ignore
    except Exception:  # noqa: BLE001
        st = None  # type: ignore[assignment]
    if st is not None:
        try:
            client = st.session_state.get("caai_api_client")
        except Exception:  # noqa: BLE001
            # session_state 在 ScriptRunContext 外不可用，回退到全局单例
            client = None
        if client is None:
            client = APIClient()
            try:
                st.session_state["caai_api_client"] = client
            except Exception:  # noqa: BLE001
                pass
        return client
    # 回退：模块级单例（无 Streamlit 环境）
    if _default_client is None:
        _default_client = APIClient()
    return _default_client


__all__ = ["APIClient", "APIError", "api_client"]
