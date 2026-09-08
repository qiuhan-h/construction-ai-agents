"""BIM API 客户端（首版 mock，阶段五接真实 BIM 平台）。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BIMConnector:
    """BIM 模型 / 构件查询客户端（首版全部返回 mock 数据）。"""

    def __init__(self, base_url: str = "https://bim.example.com/api",
                 token: str | None = None,
                 tenant_id: str = "tnt") -> None:
        self._base_url = base_url
        self._token = token
        self._tenant_id = tenant_id
        self._client: Any = None
        # 首版 mock；阶段五接真实 BIM（Forge / BIM360 / 自建平台）
        try:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=base_url, headers={"Authorization": f"Bearer {token}"} if token else {},
                timeout=30.0,
            )
        except ImportError:
            logger.warning("httpx 不可用；BIM 走 mock 模式")

    async def get_project_tree(self, project_id: str) -> list[dict]:
        """获取项目构件树。真实平台不可用/失败 → 降级 mock（K2 修复）。"""
        if self._client is None:
            return self._mock_project_tree(project_id)
        try:
            resp = await self._client.get(f"/projects/{project_id}/tree")
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return data
            logger.warning("BIM project tree 空数据 → 降级 mock")
        except Exception as e:  # noqa: BLE001
            logger.warning("BIM project tree 调用失败 → 降级 mock: %s", e)
        return self._mock_project_tree(project_id)

    async def get_element(self, element_id: str) -> dict:
        """获取构件详情。真实平台不可用/失败 → 降级 mock（K2 修复）。"""
        if self._client is None:
            return self._mock_element(element_id)
        try:
            resp = await self._client.get(f"/elements/{element_id}")
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("element_id"):
                return data
            logger.warning("BIM element 空数据 → 降级 mock")
        except Exception as e:  # noqa: BLE001
            logger.warning("BIM element 调用失败 → 降级 mock: %s", e)
        return self._mock_element(element_id)

    def _mock_element(self, element_id: str) -> dict:
        return {"element_id": element_id, "name": f"Mock-{element_id}",
                "type": "IfcBeam", "properties": {}}

    def _mock_project_tree(self, project_id: str) -> list[dict]:
        return [
            {"id": f"{project_id}-bldg-1", "type": "IfcBuilding",
             "name": "主楼", "children": [
                {"id": f"{project_id}-fl-1", "type": "IfcBuildingStorey",
                 "name": "1F", "children": []},
             ]},
        ]
