"""报告管理路由（4d 首版：内存 mock；5b.3 切换为 ORM，4d 接口契约保留）。

端点（/api/v1/reports 前缀）：
  GET    /api/v1/reports              按项目列出报告（ORM ReviewReportRepository）
  GET    /api/v1/reports/{report_id}  获取报告详情（Markdown + 签章）
  GET    /api/v1/reports/{id}/download 下载报告（首版 Markdown）

设计：
- 4d 时期：``_ReportStore`` 内存仓储；外部通过 ``get_report_store()`` 注入；
- 5b.3：新增 ``get_report_repository()`` 返回 ``ReviewReportRepository``（ORM）；
  - ``_ReportStore.get/list/add`` 内部"ORM 优先，失败回退内存"，使 4d
    单元测试 / 演示脚本（直接调 ``get_report_store()``）继续可用；
- ``report_id`` 前缀 ``rpt_`` 校验不变；
- 报告 Markdown 来源：A2AMessage.data.report.content（来自上游智能体）。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from api.dependencies.auth import AuthContext, get_auth_context
from api.schemas.pagination import Page
from api.schemas.response_schemas import ApiResponse

logger = logging.getLogger("api.routers.reports")


# =====================================================
# 5b.1：PDF 导出器（延迟构造，缺包时自动回退 Markdown）
# =====================================================
def get_pdf_exporter() -> Any:
    """延迟构造 PDFExporter；缺包时返回 None（路由层回退 Markdown）。"""
    global _PDF_EXPORTER
    if _PDF_EXPORTER is None:
        with _PDF_LOCK:
            if _PDF_EXPORTER is None:
                try:
                    from services.pdf_exporter import PDFExporter
                    _PDF_EXPORTER = PDFExporter()
                except Exception as e:  # noqa: BLE001
                    logger.warning("PDFExporter 构造失败: %s", e)
                    _PDF_EXPORTER = None
    return _PDF_EXPORTER


_PDF_EXPORTER: Any = None
_PDF_LOCK = threading.Lock()


# =====================================================
# 5b.3：ORM 仓储（首选）
# =====================================================
def _make_orm_repository() -> Any:
    """延迟构造 ORM 仓储；缺包/失败时返回 None，自动回退到内存 mock。"""
    try:
        from core.storage.sqlalchemy_repos import (
            BackendUnavailableError,
            ReviewReportRepository,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("导入 ReviewReportRepository 失败 → fallback 内存: %s", e)
        return None
    try:
        return ReviewReportRepository()
    except BackendUnavailableError as e:
        logger.warning("ReviewReportRepository 不可用 → fallback 内存: %s", e)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("ReviewReportRepository 构造失败 → fallback 内存: %s", e)
        return None


def get_report_repository() -> Any:
    """获取 ORM 仓储（每次调用 _make 一次再缓存，加锁避免并发竞态）。"""
    global _ORM_REPO
    if _ORM_REPO is None:
        with _ORM_LOCK:
            # 双重检查：拿到锁后可能已被其他线程初始化
            if _ORM_REPO is None:
                _ORM_REPO = _make_orm_repository()
    return _ORM_REPO


_ORM_REPO: Any = None
_ORM_LOCK = threading.Lock()


# =====================================================
# 4d 内存仓储（保留为兜底 + 4d 单元测试入口）
# =====================================================
class _ReportStore:
    """4d 内存 mock store；5b.3 起内部桥接到 ORM。"""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add(self, item: dict[str, Any]) -> None:
        rid = item.get("report_id")
        if not rid:
            return
        # 1) ORM 优先
        repo = get_report_repository()
        if repo is not None:
            try:
                repo.add(item)
                logger.debug("ORM upsert 报告: %s", rid)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "ORM 写入失败（%s）→ fallback 内存: rid=%s", e, rid
                )
        # 2) 内存同步（4d 兼容 / 单元测试）
        with self._lock:
            self._items[rid] = item

    def get(self, report_id: str) -> dict[str, Any] | None:
        # 1) ORM 优先
        repo = get_report_repository()
        if repo is not None:
            try:
                item = repo.get(report_id)  # 不带 tenant_id（路由层校验）
                if item is not None:
                    return item
            except Exception as e:  # noqa: BLE001
                logger.debug("ORM get 失败（%s）→ fallback 内存", e)
        # 2) 内存兜底
        with self._lock:
            return self._items.get(report_id)

    def list(
        self,
        tenant_id: str,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        # 1) ORM 优先
        repo = get_report_repository()
        if repo is not None:
            try:
                items, total = repo.list(
                    tenant_id=tenant_id, project_id=project_id,
                    limit=limit, offset=offset,
                )
                return items, total
            except Exception as e:  # noqa: BLE001
                logger.debug("ORM list 失败（%s）→ fallback 内存", e)
        # 2) 内存兜底
        with self._lock:
            items = [it for it in self._items.values() if it.get("tenant_id") == tenant_id]
        if project_id:
            items = [it for it in items if it.get("project_id") == project_id]
        total = len(items)
        items = items[offset : offset + limit]
        return items, total


_REPORT_STORE = _ReportStore()


def get_report_store() -> _ReportStore:
    return _REPORT_STORE


# 兼容 4d 单元测试：暴露 reset
def _reset_report_store() -> None:
    with _REPORT_STORE._lock:
        _REPORT_STORE._items.clear()


# =====================================================
# 路由
# =====================================================
def build_reports_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

    @router.get("", response_model=ApiResponse[dict])
    async def list_reports(
        project_id: str | None = Query(default=None, description="按项目过滤"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200),
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        store = get_report_store()
        offset = (page - 1) * page_size
        items, total = store.list(auth.tenant_id, project_id, page_size, offset)
        return ApiResponse[dict].ok(
            Page.of(
                [
                    {
                        "report_id": it.get("report_id"),
                        "tenant_id": it.get("tenant_id"),
                        "project_id": it.get("project_id"),
                        "title": it.get("title"),
                        "conclusion": it.get("conclusion"),
                        "status": it.get("status"),
                        "created_at": it.get("created_at"),
                    }
                    for it in items
                ],
                total,
                page=page,
                page_size=page_size,
            ).model_dump()
        )

    @router.get("/{report_id}", response_model=ApiResponse[dict])
    async def get_report(
        report_id: str,
        auth: AuthContext = Depends(get_auth_context),
    ) -> ApiResponse[dict[str, Any]]:
        if not report_id.startswith("rpt_"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "10002", "message": "report_id 必须以 rpt_ 开头"},
            )
        item = get_report_store().get(report_id)
        if item is None or item.get("tenant_id") != auth.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "10003", "message": f"报告不存在: {report_id}"},
            )
        return ApiResponse[dict].ok(item)

    @router.get("/{report_id}/download")
    async def download_report(
        report_id: str,
        format: str = Query(default="md", description="md（默认）| pdf（5b.1）"),
        auth: AuthContext = Depends(get_auth_context),
    ) -> Any:
        if not report_id.startswith("rpt_"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "10002", "message": "report_id 必须以 rpt_ 开头"},
            )
        item = get_report_store().get(report_id)
        if item is None or item.get("tenant_id") != auth.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "10003", "message": f"报告不存在: {report_id}"},
            )
        fmt = (format or "md").lower()
        if fmt not in ("md", "pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "10002", "message": f"不支持的格式: {format}"},
            )
        content = item.get("content") or ""
        title = item.get("title") or report_id
        if fmt == "pdf":
            exporter = get_pdf_exporter()
            if exporter is not None:
                result = await exporter.export(
                    report_id, title, content,
                    meta={
                        "tenant_id": item.get("tenant_id"),
                        "project_id": item.get("project_id"),
                        "signature": item.get("signature"),
                    },
                    force_format="pdf",
                )
                media_type = (
                    "application/pdf" if result.format == "pdf"
                    else "text/markdown"
                )
                headers = {
                    "Content-Disposition":
                        f'attachment; filename="{result.filename}"'
                }
                if result.warning:
                    headers["X-Export-Warning"] = result.warning
                return Response(
                    content=result.bytes,
                    media_type=media_type,
                    headers=headers,
                )
            # PDFExporter 不可用 → 回退 Markdown JSON 响应
        # 默认 md：返回 JSON 包装（保留 4d 接口契约）
        return ApiResponse[dict].ok(
            {
                "report_id": report_id,
                "format": "md",
                "size": len(content),
                "content": content,
                "signature": item.get("signature"),
            }
        )

    return router


__all__ = [
    "build_reports_router",
    "get_report_store",
    "get_report_repository",
    "_reset_report_store",
]
