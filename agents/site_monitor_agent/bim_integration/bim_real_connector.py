"""BIM 真实客户端：Autodesk Platform Services (Forge / BIM360)（5b.5）。

设计：
- 接 Autodesk Platform Services (APS，原 Forge) BIM360 API；
- OAuth 2.0 ``client_credentials`` 派发 token，自动刷新（默认 1h TTL）；
- 提供与 4c ``BIMConnector`` 兼容的接口（``get_project_tree`` / ``get_element``）
  + 扩展 ``list_elements`` / ``download_ifc``；
- 缺 ``client_id`` / ``client_secret`` / ``hub_id`` / ``project_id``
  → **降级 Mock** + 警告（与 ``bim_connector.py`` 行为一致）；
- 网络错 / 非 2xx → 降级 Mock（不抛异常给上游）。

参考：
- https://aps.autodesk.com/developer-guide
- https://aps.autodesk.com/en/docs/oauth/v2/developers_guide/overview/
- https://aps.autodesk.com/en/docs/data/v2/reference/http/projects-GET/
- https://aps.autodesk.com/en/docs/model-derivative/v2
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Autodesk Platform Services 公共端点
_APS_AUTH_ENDPOINT = "https://developer.api.autodesk.com/authentication/v2/token"
_APS_DEFAULT_BASE = "https://developer.api.autodesk.com"
_DEFAULT_SCOPE = "data:read bucket:read"
_TOKEN_REFRESH_AHEAD = 60  # 提前 60 秒刷新 token，避免边界失效


def _is_placeholder(value: Any) -> bool:
    """判断是否占位（与 base_channel.is_placeholder 同义，避免循环导入）。"""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    v = value.strip()
    return not v or v in {"需要补充实际链接", "xxx", "your-client-id"}


def _http_post_form(
    url: str,
    form: dict[str, str],
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """标准库 POST application/x-www-form-urlencoded。返回 (status, body)。"""
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "caai-bim-connector/1.0",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"POST {url} 失败: {e}") from e


def _http_get_json(
    url: str,
    *,
    access_token: str,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """标准库 GET，返回 (status, parsed_json_or_text)。"""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "caai-bim-connector/1.0",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except Exception:  # noqa: BLE001
                return resp.status, body
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"GET {url} 失败: {e}") from e


class BIMRealConnector:
    """Autodesk Platform Services (BIM360 / Forge) 真实客户端。

    与 4c ``BIMConnector`` 兼容（``get_project_tree`` / ``get_element``）+ 扩展方法。
    缺凭据 / 网络失败时降级 Mock，保证上游 ``ProgressTracker`` 可离线运行。
    """

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        hub_id: str | None = None,
        project_id: str | None = None,
        base_url: str = _APS_DEFAULT_BASE,
        scope: str = _DEFAULT_SCOPE,
        timeout: float = 15.0,
        force_mock: bool = False,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._hub_id = hub_id
        self._project_id = project_id
        self._base_url = base_url.rstrip("/")
        self._scope = scope
        self._timeout = timeout
        self.force_mock = force_mock

        # token 缓存（_cached_at + _cached_expires_in）
        self._access_token: str | None = None
        self._token_obtained_at: float = 0.0
        self._token_expires_in: int = 0

    # =====================================================
    # 凭据检查 + Mock 降级
    # =====================================================
    def _has_credentials(self) -> bool:
        if self.force_mock:
            return False
        for v in (
            self._client_id,
            self._client_secret,
            self._hub_id,
            self._project_id,
        ):
            if _is_placeholder(v) or not v:
                return False
        return True

    def _mock_project_tree(self, project_id: str) -> list[dict]:
        """与 4c ``BIMConnector._mock_project_tree`` 行为兼容。"""
        return [
            {
                "id": f"{project_id}-bldg-1",
                "type": "IfcBuilding",
                "name": "主楼",
                "children": [
                    {
                        "id": f"{project_id}-fl-1",
                        "type": "IfcBuildingStorey",
                        "name": "1F",
                        "children": [],
                    },
                ],
            },
        ]

    def _mock_element(self, element_id: str) -> dict:
        return {
            "element_id": element_id,
            "name": f"Mock-{element_id}",
            "type": "IfcBeam",
            "properties": {},
        }

    # =====================================================
    # OAuth 2.0 client_credentials
    # =====================================================
    async def _ensure_token(self) -> str | None:
        """获取 / 刷新 access token；失败返回 None（触发 Mock 降级）。"""
        if not self._has_credentials():
            return None
        # 还在有效期（提前 60s 刷新）
        if (
            self._access_token
            and self._token_obtained_at
            and (time.time() - self._token_obtained_at) < (self._token_expires_in - _TOKEN_REFRESH_AHEAD)
        ):
            return self._access_token

        try:
            form = {
                "grant_type": "client_credentials",
                "client_id": self._client_id or "",
                "client_secret": self._client_secret or "",
                "scope": self._scope,
            }
            status, body = await asyncio.to_thread(
                _http_post_form,
                _APS_AUTH_ENDPOINT,
                form,
                timeout=self._timeout,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("BIM OAuth token 获取失败: %s → 降级 Mock", e)
            return None

        if not (200 <= status < 300):
            logger.warning("BIM OAuth 非 2xx: status=%s body=%s → 降级 Mock", status, body[:120])
            return None

        try:
            data = json.loads(body) if isinstance(body, str) else body
            self._access_token = data.get("access_token")
            self._token_expires_in = int(data.get("expires_in", 3600))
            self._token_obtained_at = time.time()
            logger.debug("BIM token 刷新成功，expires_in=%ss", self._token_expires_in)
            return self._access_token
        except Exception as e:  # noqa: BLE001
            logger.warning("BIM OAuth 响应解析失败: %s → 降级 Mock", e)
            return None

    # =====================================================
    # 业务方法（与 BIMConnector 兼容）
    # =====================================================
    async def get_project_tree(self, project_id: str | None = None) -> list[dict]:
        """获取项目构件树。

        APS 路径：``GET /data/v1/projects/{project_id}/topFolders``
        降级：缺凭据 / 网络错 → 返回 ``_mock_project_tree``。
        """
        if not self._has_credentials():
            return self._mock_project_tree(project_id or self._project_id or "mock")

        pid = project_id or self._project_id or ""
        token = await self._ensure_token()
        if not token:
            return self._mock_project_tree(pid)

        url = f"{self._base_url}/data/v1/projects/{pid}/topFolders"
        try:
            status, resp = await asyncio.to_thread(
                _http_get_json, url, access_token=token, timeout=self._timeout,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("BIM get_project_tree 失败: %s → 降级 Mock", e)
            return self._mock_project_tree(pid)

        if not (200 <= status < 300):
            logger.warning("BIM get_project_tree 非 2xx: status=%s → 降级 Mock", status)
            return self._mock_project_tree(pid)

        # 响应形如 {"data":[{"id","type","attributes":{"name","displayName"},...}]}
        if not isinstance(resp, dict):
            return self._mock_project_tree(pid)
        items = resp.get("data", []) if isinstance(resp.get("data"), list) else []
        tree: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes", {}) if isinstance(item.get("attributes"), dict) else {}
            tree.append({
                "id": item.get("id", ""),
                "type": item.get("type", "folder"),
                "name": attrs.get("name") or attrs.get("displayName", ""),
                "children": [],
            })
        return tree or self._mock_project_tree(pid)

    async def get_element(self, element_id: str) -> dict:
        """获取单个构件详情（兼容 4c ``BIMConnector.get_element``）。

        APS 路径：``GET /modelderivative/v2/designdata/{urn}/metadata/{guid}``
        本方法首版接受 ``urn:element_id`` 形式的 ``element_id``，便于传 URN + GUID。
        """
        if not self._has_credentials():
            return self._mock_element(element_id)

        token = await self._ensure_token()
        if not token:
            return self._mock_element(element_id)

        # element_id 形如 "urn:guid"，自动拆分
        if ":" in element_id:
            urn, guid = element_id.split(":", 1)
        else:
            urn, guid = element_id, element_id

        url = (
            f"{self._base_url}/modelderivative/v2/designdata/"
            f"{urllib.parse.quote(urn, safe='')}/metadata/{urllib.parse.quote(guid, safe='')}"
        )
        try:
            status, resp = await asyncio.to_thread(
                _http_get_json, url, access_token=token, timeout=self._timeout,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("BIM get_element 失败: %s → 降级 Mock", e)
            return self._mock_element(element_id)

        if not (200 <= status < 300):
            logger.warning("BIM get_element 非 2xx: status=%s → 降级 Mock", status)
            return self._mock_element(element_id)

        if not isinstance(resp, dict):
            return self._mock_element(element_id)
        data = resp.get("data", {}) if isinstance(resp.get("data"), dict) else {}
        attrs = data.get("attributes", {}) if isinstance(data.get("attributes"), dict) else {}
        return {
            "element_id": guid,
            "name": attrs.get("name", attrs.get("displayName", f"Element-{guid}")),
            "type": attrs.get("type", "IfcElement"),
            "properties": attrs,
        }

    async def list_elements(
        self,
        project_id: str | None = None,
        *,
        type_filter: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """列出项目构件（5b.5 扩展，给 ProgressTracker 用）。

        APS 路径：``GET /data/v1/projects/{project_id}/items``
        """
        if not self._has_credentials():
            return [self._mock_element(f"mock-{i+1}") for i in range(min(limit, 3))]

        pid = project_id or self._project_id or ""
        token = await self._ensure_token()
        if not token:
            return [self._mock_element(f"mock-{i+1}") for i in range(min(limit, 3))]

        params: dict[str, str] = {"page[limit]": str(max(1, min(limit, 200)))}
        if type_filter:
            params["filter[attributes.extension.type]"] = type_filter
        qs = urllib.parse.urlencode(params)
        url = f"{self._base_url}/data/v1/projects/{pid}/items?{qs}"

        try:
            status, resp = await asyncio.to_thread(
                _http_get_json, url, access_token=token, timeout=self._timeout,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("BIM list_elements 失败: %s → 降级 Mock", e)
            return [self._mock_element(f"mock-{i+1}") for i in range(min(limit, 3))]

        if not (200 <= status < 300) or not isinstance(resp, dict):
            return [self._mock_element(f"mock-{i+1}") for i in range(min(limit, 3))]

        items = resp.get("data", []) if isinstance(resp.get("data"), list) else []
        out: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes", {}) if isinstance(item.get("attributes"), dict) else {}
            out.append({
                "element_id": item.get("id", ""),
                "name": attrs.get("name") or attrs.get("displayName", ""),
                "type": item.get("type", "IfcElement"),
                "properties": attrs,
            })
        return out or [self._mock_element(f"mock-{i+1}") for i in range(min(limit, 3))]

    async def download_ifc(
        self,
        project_id: str | None = None,
        item_id: str | None = None,
        out_path: str | None = None,
    ) -> bytes:
        """下载 IFC 文件内容（5b.5 扩展，给 ifc_real_parser 用）。

        APS 路径：``GET /data/v1/projects/{project_id}/items/{item_id}/tip``（顶版本）
        缺凭据 / 失败 → 返回空 bytes（调用方应检测后走 Mock）。
        """
        if not self._has_credentials() or not item_id:
            return b""

        pid = project_id or self._project_id or ""
        token = await self._ensure_token()
        if not token:
            return b""

        url = f"{self._base_url}/data/v1/projects/{pid}/items/{urllib.parse.quote(item_id, safe='')}/tip"
        try:
            status, resp = await asyncio.to_thread(
                _http_get_json, url, access_token=token, timeout=self._timeout,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("BIM download_ifc 失败: %s", e)
            return b""

        if not (200 <= status < 300) or not isinstance(resp, dict):
            return b""

        # tip 响应里包含 storage URL；首版仅返回占位 bytes（真实下载需要二次拉 storage）
        data = resp.get("data", {}) if isinstance(resp.get("data"), dict) else {}
        relationships = data.get("relationships", {}) if isinstance(data.get("relationships"), dict) else {}
        storage_meta = relationships.get("storage", {}) if isinstance(relationships.get("storage"), dict) else {}
        storage_link = storage_meta.get("links", {}).get("related", {}).get("href", "")
        if not storage_link:
            return b""

        # 二次拉 storage 内容（原始 IFC 字节）— 用 asyncio.to_thread 避免阻塞 event loop
        def _http_get_bytes(url: str, *, access_token: str, timeout: float,
                            accept: str = "application/octet-stream") -> bytes:
            req = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": accept,
                    "User-Agent": "caai-bim-connector/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp2:  # noqa: S310
                return resp2.read()

        try:
            content = await asyncio.to_thread(
                _http_get_bytes, storage_link,
                access_token=token, timeout=self._timeout,
            )
        except (urllib.error.URLError, TimeoutError) as e:
            logger.warning("BIM storage 下载失败: %s", e)
            return b""

        if out_path:
            try:
                with open(out_path, "wb") as f:
                    f.write(content)
            except OSError as e:  # noqa: BLE001
                logger.warning("BIM IFC 落盘失败: %s", e)
        return content

    # =====================================================
    # 便捷方法
    # =====================================================
    def is_mock_mode(self) -> bool:
        """暴露给健康检查 / Dashboard：当前是否走 Mock 模式。"""
        return not self._has_credentials()


def make_bim_real_connector(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    hub_id: str | None = None,
    project_id: str | None = None,
    **kwargs: Any,
) -> BIMRealConnector:
    """工厂函数（与 ``BIMConnector`` 一致的构造风格）。

    全部参数未显式传入时，从 ``config.settings``（.env 的 APS_* 变量）读取；
    凭据缺失 / 占位时由 ``BIMRealConnector`` 内部自动降级 mock。
    """
    if client_id is None and client_secret is None and hub_id is None and project_id is None:
        try:
            from config import get_settings

            s = get_settings()
            client_id = s.aps_client_id or None
            client_secret = s.aps_client_secret.get_secret_value() or None
            hub_id = s.aps_hub_id or None
            project_id = s.aps_project_id or None
        except Exception:  # noqa: BLE001
            pass
    return BIMRealConnector(
        client_id=client_id,
        client_secret=client_secret,
        hub_id=hub_id,
        project_id=project_id,
        **kwargs,
    )


__all__ = [
    "BIMRealConnector",
    "make_bim_real_connector",
]
