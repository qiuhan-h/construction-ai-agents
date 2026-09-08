"""租户 SQL 中间件（6b.2 多租户 ORM 自动注入）。

设计：
- ``TenantContext`` 基于 contextvars 存储当前请求的 tenant_id；
- ``TenantMiddleware.intercept_sql(sql, params)`` 用 sqlparse 解析 SELECT，
  自动注入 ``WHERE tenant_id = ?``（或 ``AND tenant_id = ?``）；
- SQLAlchemy ``before_cursor_execute`` 事件钩子自动调用 intercept_sql；
- 无 sqlparse 时降级为字符串拼接（足够 SQLite 测试用）；
- 无 tenant_id 时透传原 SQL（由上层 auth 依赖负责设置）。

约束：
- 仅拦截 SELECT；INSERT/UPDATE/DELETE 由 ORM 模型的 default/context 处理；
- 已含 tenant_id 条件的 SQL 不重复注入；
- 参数以命名参数 ``:tenant_id`` / ``%s`` 形式追加到 params dict。
"""

from __future__ import annotations

import logging
import re
import threading
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger("core.storage.tenant_middleware")

# 当前租户上下文变量（请求级隔离）
_tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)

# 需要自动注入 tenant_id 的表（TenantMixin 的子类表）
_TENANT_TABLES: set[str] = {
    "projects",
    "construction_plans",
    "inspections",
    "review_reports",
    "violations",
    "alerts",
    "sensor_devices",
    "geofences",
    "geofence_violations",
    "usage_records",
    "bills",
}

# 参数占位符（SQLite / PostgreSQL 通用）
_PARAM_KEY = "_tenant_id"


class TenantContext:
    """请求级租户上下文（基于 contextvars，async 安全）。"""

    @staticmethod
    def set_tenant_id(tenant_id: str | None) -> None:
        _tenant_id_var.set(tenant_id)

    @staticmethod
    def get_tenant_id() -> str | None:
        return _tenant_id_var.get()

    @staticmethod
    def clear() -> None:
        _tenant_id_var.set(None)


class TenantMiddleware:
    """SQL 自动注入租户过滤中间件。"""

    def __init__(self) -> None:
        self._registered = False
        self._lock = threading.Lock()

    def intercept_sql(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> tuple[str, dict[str, Any]]:
        """对 SELECT 语句注入 WHERE tenant_id = :_tenant_id。

        返回 (modified_sql, modified_params)；
        无 tenant_id 或非 SELECT 或已含 tenant_id → 原样返回。
        """
        tenant_id = TenantContext.get_tenant_id()
        if not tenant_id:
            return sql, dict(params or {})

        stripped = sql.strip()
        # 仅拦截 SELECT
        if not stripped.upper().startswith("SELECT"):
            return sql, dict(params or {})

        # 检查是否已含 tenant_id 条件（避免重复注入）
        if re.search(r"\btenant_id\b", sql, re.IGNORECASE):
            return sql, dict(params or {})

        # 检查是否涉及租户表
        if not self._involves_tenant_tables(sql):
            return sql, dict(params or {})

        new_params = dict(params or {})
        new_params[_PARAM_KEY] = tenant_id

        # 尝试用 sqlparse 精确注入；不可用时降级为字符串拼接
        modified = self._inject_with_sqlparse(sql, new_params)
        if modified is not None:
            return modified, new_params
        return self._inject_fallback(sql, new_params), new_params

    def register_engine(self, engine: Any) -> None:
        """注册 SQLAlchemy before_cursor_execute 事件钩子。"""
        with self._lock:
            if self._registered:
                return
            from sqlalchemy import event

            @event.listens_for(engine, "before_cursor_execute")
            def _before_cursor_execute(
                conn: Any,
                cursor: Any,
                statement: str,
                parameters: Any,
                context: Any,
                executemany: bool,
            ) -> tuple[str, Any]:
                # 参数可能是 dict 或 tuple；统一处理为 dict
                params: dict[str, Any] = {}
                if isinstance(parameters, dict):
                    params = dict(parameters)
                elif isinstance(parameters, (tuple, list)) and parameters:
                    # 位置参数 → 转为命名参数（仅当注入时需要追加）
                    params = {f"arg_{i}": v for i, v in enumerate(parameters)}

                new_sql, new_params = self.intercept_sql(statement, params)

                # 如果参数格式变了，需要转换回原始格式
                if isinstance(parameters, dict):
                    return new_sql, new_params
                elif isinstance(parameters, (tuple, list)) and parameters:
                    # 位置参数：追加 tenant_id 到末尾
                    return new_sql, tuple(parameters) + (new_params.get(_PARAM_KEY),)
                else:
                    return new_sql, new_params

            self._registered = True
            logger.info("tenant_middleware 已注册到 engine")

    # ---------- 内部 ----------
    @staticmethod
    def _involves_tenant_tables(sql: str) -> bool:
        """检查 SQL 是否涉及租户表。"""
        sql_lower = sql.lower()
        return any(table in sql_lower for table in _TENANT_TABLES)

    @staticmethod
    def _inject_with_sqlparse(
        sql: str, params: dict[str, Any]
    ) -> str | None:
        """用 sqlparse 精确注入 WHERE 子句。"""
        try:
            import sqlparse
        except ImportError:
            return None

        try:
            parsed = sqlparse.parse(sql)
            if not parsed:
                return None

            # 简化处理：找 WHERE 关键字位置
            tokens = list(parsed[0].flatten())
            where_idx = None
            for i, token in enumerate(tokens):
                if token.is_keyword and token.normalized == "WHERE":
                    where_idx = i
                    break

            placeholder = f":{_PARAM_KEY}"
            if where_idx is not None:
                # 已有 WHERE → 在 WHERE 后插入 AND tenant_id = :_tenant_id
                insert_token = sqlparse.tokens.Whitespace(" ")
                and_token = sqlparse.tokens.Keyword("AND")
                cond = f" tenant_id = {placeholder}"
                tokens.insert(where_idx + 1, sqlparse.tokens.Keyword(cond))
                return "".join(str(t) for t in tokens)
            else:
                # 无 WHERE → 在 FROM ... 之后追加 WHERE tenant_id = :_tenant_id
                # 找 FROM 后第一个条件位置
                result = sql
                # 找到 FROM 子句后的表名，在其后追加 WHERE
                # 简单策略：在 SQL 末尾追加 WHERE（适用于无 GROUP BY/ORDER BY 的情况）
                # 更安全：在 ORDER BY / GROUP BY / LIMIT 之前插入
                for kw in (" ORDER BY", " GROUP BY", " LIMIT", " HAVING"):
                    idx = result.upper().find(kw)
                    if idx != -1:
                        result = (
                            result[:idx]
                            + f" WHERE tenant_id = {placeholder}"
                            + result[idx:]
                        )
                        return result
                # 末尾追加
                return result.rstrip(";") + f" WHERE tenant_id = {placeholder}"
        except Exception as e:  # noqa: BLE001
            logger.debug("sqlparse 注入失败 → 降级: %s", e)
            return None

    @staticmethod
    def _inject_fallback(sql: str, params: dict[str, Any]) -> str:
        """无 sqlparse 时的降级注入。"""
        placeholder = f":{_PARAM_KEY}"
        sql_upper = sql.upper()

        # 已有 WHERE → 追加 AND
        where_match = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
        if where_match:
            pos = where_match.end()
            return sql[:pos] + f" AND tenant_id = {placeholder}" + sql[pos:]

        # 无 WHERE → 在 ORDER BY / GROUP BY / LIMIT 之前插入
        for kw in (" ORDER BY", " GROUP BY", " LIMIT", " HAVING"):
            idx = sql_upper.find(kw)
            if idx != -1:
                return sql[:idx] + f" WHERE tenant_id = {placeholder}" + sql[idx:]

        # 末尾追加
        return sql.rstrip(";") + f" WHERE tenant_id = {placeholder}"


# =====================================================
# 单例 + 测试重置
# =====================================================
_middleware: TenantMiddleware | None = None


def get_tenant_middleware() -> TenantMiddleware:
    global _middleware
    if _middleware is None:
        _middleware = TenantMiddleware()
    return _middleware


def reset_tenant_middleware() -> None:
    global _middleware
    _middleware = None


__all__ = [
    "TenantContext",
    "TenantMiddleware",
    "get_tenant_middleware",
    "reset_tenant_middleware",
]
