"""编排器 HTTP 路由（4d）。

端点（/api/v1/orchestrator 前缀）：
  GET  /api/v1/orchestrator/workflows                 列出已注册工作流
  POST /api/v1/orchestrator/workflows/{name}/trigger  手动触发工作流
  GET  /api/v1/orchestrator/runs/{run_id}             查询运行状态
  GET  /api/v1/orchestrator/timeline                  当前租户协作时间线

设计：
- 4d 不暴露 ``create / delete`` workflow（仅消费 4c 内置工作流）；
- ``/trigger`` 接收 payload dict，渲染工作流参数并启动执行；
- payload 同时支持：
  - query ``?payload={"alert_id":"a1"}``（URL 兼容）
  - body JSON ``{"payload": {...}}``（推荐）
  兼容性：query 优先（无 body 时也接受），body JSON 次之；
- ``/runs/{run_id}`` 走 WorkflowEngine.get_run()（内存）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from api.dependencies.auth import AuthContext, get_auth_context
from api.dependencies.orchestrator_provider import get_orchestrator
from api.schemas.response_schemas import ApiResponse
from common.exceptions import AppException

logger = logging.getLogger("api.routers.orchestrator")


def _raise_from_app_exc(exc: AppException) -> None:
    raise HTTPException(status_code=exc.http_status, detail=exc.to_dict())


def _coerce_payload(raw: Any) -> dict[str, Any] | None:
    """把 query / body 中的 payload 归一化为 dict。

    - 已是 dict → 直接返回；
    - 是 str 且可解析为 JSON → 反序列化；
    - 是 str 不可解析 / None / 其他类型 → 返回 None。
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None
    return None


def build_orchestrator_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/orchestrator", tags=["orchestrator"])

    @router.get("/workflows", response_model=ApiResponse[dict])
    async def list_workflows(
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        orch = get_orchestrator()
        items = orch.list_workflows()
        return ApiResponse[dict].ok({"workflows": items, "total": len(items)})

    @router.get("/workflows/{name}", response_model=ApiResponse[dict])
    async def get_workflow(
        name: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        """读取单个工作流的完整定义（节点 + 依赖 + 参数模板）。

        4e 起供编排可视化 dashboard 详情面板使用。
        """
        orch = get_orchestrator()
        try:
            wf = orch.workflow_engine.get(name)
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "10003", "message": f"工作流未注册: {e}"},
            ) from e
        return ApiResponse[dict].ok(
            {
                "name": wf.name,
                "description": wf.description,
                "nodes": [
                    {
                        "node_id": n.node_id,
                        "kind": n.kind,
                        "agent_name": n.agent_name,
                        "method": n.method,
                        "system_action": n.system_action,
                        "depends_on": list(n.depends_on),
                        "params": dict(n.params),
                        "retry": n.retry,
                        "timeout_seconds": n.timeout_seconds,
                    }
                    for n in wf.nodes
                ],
            }
        )

    @router.post(
        "/workflows/{name}/trigger", response_model=ApiResponse[dict]
    )
    async def trigger_workflow(
        name: str,
        payload: str | None = None,
        body: dict[str, Any] | None = Body(default=None),
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        # 解析 payload：query 字符串优先（兼容 URL 调用），否则 body JSON
        merged: dict[str, Any] = {}
        qp = _coerce_payload(payload)
        if qp is not None:
            merged.update(qp)
        if isinstance(body, dict):
            bp = body.get("payload")
            if isinstance(bp, dict):
                merged.update(bp)
            elif body:
                # 也兼容直接把业务字段平铺在 body 顶层（payload 节点无嵌套）
                merged.update(body)
        if payload is not None and qp is None and "{" in payload and "}" in payload:
            # 给了 query 但 JSON 解析失败 → 400
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "10002",
                    "message": f"payload 不是合法 JSON: {payload[:120]}",
                },
            )

        orch = get_orchestrator()
        try:
            run_id = await orch.trigger_workflow(
                name=name, payload=merged, tenant_id=auth.tenant_id
            )
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "10003", "message": f"工作流未注册: {e}"},
            ) from e
        except AppException as e:
            _raise_from_app_exc(e)
        except ValueError as e:
            # 工作流模板变量缺失 / 拓扑环 / 节点类型非法 → 400
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "10002",
                    "message": f"工作流参数非法: {e}",
                    "data": {"workflow": name, "payload": merged},
                },
            ) from e
        return ApiResponse[dict].ok(
            {
                "run_id": run_id,
                "workflow": name,
                "tenant_id": auth.tenant_id,
                "state": "running",
            }
        )

    @router.get("/runs/{run_id}", response_model=ApiResponse[dict])
    async def get_run(
        run_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        orch = get_orchestrator()
        info = orch.get_run(run_id)
        if info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "10003", "message": f"运行不存在: {run_id}"},
            )
        # 租户隔离
        if info.get("tenant_id") != auth.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "30002", "message": "无权访问该 run"},
            )
        return ApiResponse[dict].ok({"run_id": run_id, **info})

    @router.get("/timeline", response_model=ApiResponse[dict])
    async def get_timeline(
        auth: AuthContext = Depends(get_auth_context),
        limit: int | None = Query(
            default=None, ge=1, le=500, description="最多返回条数（按 ts 倒序）"
        ),
    ) -> ApiResponse[dict[str, Any]]:
        orch = get_orchestrator()
        items = orch.collaboration.get_timeline_by_tenant(auth.tenant_id)
        # 按 ts 倒序
        items.sort(key=lambda x: x.get("ts") or "", reverse=True)
        if limit is not None:
            items = items[:limit]
        return ApiResponse[dict].ok(
            {
                "tenant_id": auth.tenant_id,
                "timeline": items,
                "total": len(items),
                "truncated": limit is not None,
            }
        )

    @router.get("/stats", response_model=ApiResponse[dict])
    async def get_stats(
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        """编排器运行统计（4e dashboard 使用）。

        返回 workflow 数 / 运行总数 / 今日触发 / 失败 / 最近 run。
        """
        orch = get_orchestrator()
        info = orch.stats(tenant_id=auth.tenant_id)
        return ApiResponse[dict].ok(info)

    return router


__all__ = ["build_orchestrator_router"]
