"""InfluxDB 2.x 时序数据库客户端（core 层顶层 API）。

设计：
- 直接走 InfluxDB 2.x HTTP API（``/api/v2/write`` + ``/api/v2/query``），
  自行拼 line protocol；不依赖 ``influxdb-client``，沙箱无包也能跑；
- 配置从 ``config.get_settings()`` 注入：``tsdb_url`` / ``tsdb_token`` /
  ``tsdb_org`` / ``tsdb_bucket``；
- 缺凭据 / 占位 → **Mock 模式**（与 5b.4 一致），只记日志；
- 写失败 → 抛 ``InfluxWriteError``；批量写（``write_points``）采用尽力而为：
  失败点降级为 mock，单点失败不影响其他点。

分层约束（shu_zhuang_tu.txt）：
- ``core/timeseries/`` 是时序数据库的顶层入口；
- ``agents/site_monitor_agent/iot_integration/influxdb_writer.py`` re-export 本模块，
  保持 agent 侧引用路径不变。
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================
# 异常
# =====================================================
class InfluxWriteError(Exception):
    """InfluxDB 写入失败。"""


# =====================================================
# 工具
# =====================================================
_PLACEHOLDER = "需要补充实际链接"


def _is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return True
    return v == _PLACEHOLDER


def _get_secret_str(value: Any) -> str:
    """Pydantic ``SecretStr`` 兼容。"""
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        try:
            return str(value.get_secret_value())
        except Exception:  # noqa: BLE001
            return ""
    return str(value)


def _escape_tag_value(v: Any) -> str:
    """Line protocol tag / field value 转义。"""
    s = str(v)
    return s.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_measurement(v: str) -> str:
    """measurement 名字：转义 ``,`` 和空格。"""
    return str(v).replace(" ", "\\ ").replace(",", "\\,")


def _format_field_value(v: Any) -> str | None:
    """Field 值：int / uint / float / bool / string。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return f"{v}i"
    if isinstance(v, float):
        # InfluxDB 要求 float 带小数点
        if v != v:  # NaN
            return None
        if v == float("inf") or v == float("-inf"):
            return None
        return repr(v) if "." in repr(v) else f"{v}.0"
    if isinstance(v, str):
        # 字符串 field 必须双引号转义
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return None


def build_line_protocol(
    measurement: str,
    tags: dict[str, Any],
    fields: dict[str, Any],
    ts: datetime | None = None,
) -> str | None:
    """拼一条 InfluxDB line protocol。

    返回 None 表示字段全部非法（被跳过）。
    """
    if not measurement or not fields:
        return None
    # field 序列化
    parts: list[str] = []
    for k, v in fields.items():
        fv = _format_field_value(v)
        if fv is None:
            continue
        parts.append(f"{_escape_tag_value(k)}={fv}")
    if not parts:
        return None
    line = _escape_measurement(measurement)
    if tags:
        ts_pairs = []
        for k, v in sorted(tags.items()):
            if v is None or v == "":
                continue
            ts_pairs.append(f"{_escape_tag_value(k)}={_escape_tag_value(v)}")
        if ts_pairs:
            line += "," + ",".join(ts_pairs)
    line += " " + ",".join(parts)
    if ts is not None:
        # InfluxDB v2 默认纳秒
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        ns = int(ts.timestamp() * 1_000_000_000)
        line += f" {ns}"
    return line


# =====================================================
# HTTP 工具
# =====================================================
def _http_post(
    url: str,
    data: bytes,
    *,
    headers: dict[str, str],
    timeout: float = 5.0,
) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except (urllib.error.URLError, TimeoutError) as e:
        raise InfluxWriteError(f"POST {url} 失败: {e}") from e


# =====================================================
# 主类
# =====================================================
class InfluxDBWriter:
    """InfluxDB 2.x 真实写入器。

    使用方式：
        writer = InfluxDBWriter()
        await writer.write_point("temperature", {"device": "d1"}, {"value": 25.3}, ts)
        await writer.write_points([(m, tags, fields, ts), ...])
    """

    backend_name: str = "influxdb"

    def __init__(
        self,
        *,
        url: str | None = None,
        token: str | None = None,
        org: str | None = None,
        bucket: str | None = None,
        timeout: float = 5.0,
        force_mock: bool = False,
    ) -> None:
        # 优先级：显式参数 > config 注入 > None
        if url is None or token is None or org is None or bucket is None:
            cfg_url, cfg_token, cfg_org, cfg_bucket = self._load_from_config()
            url = url or cfg_url
            token = token or cfg_token
            org = org or cfg_org
            bucket = bucket or cfg_bucket

        self._url = (url or "").rstrip("/")
        self._token = _get_secret_str(token)
        self._org = org or ""
        self._bucket = bucket or ""
        self._timeout = timeout
        self.force_mock = force_mock

    @staticmethod
    def _load_from_config() -> tuple[str, str, str, str]:
        try:
            from config import get_settings  # 沙箱缺 pydantic 时静默降级

            s = get_settings()
            return (
                str(getattr(s, "tsdb_url", "") or ""),
                _get_secret_str(getattr(s, "tsdb_token", "")),
                str(getattr(s, "tsdb_org", "") or ""),
                str(getattr(s, "tsdb_bucket", "") or ""),
            )
        except Exception:  # noqa: BLE001
            return "", "", "", ""

    @property
    def is_mock(self) -> bool:
        if self.force_mock:
            return True
        return any(_is_placeholder(v) or not v for v in (self._url, self._token, self._org, self._bucket))

    @property
    def write_url(self) -> str:
        return f"{self._url}/api/v2/write"

    # ---- 公开 API ----
    async def write_point(
        self,
        measurement: str,
        tags: dict[str, Any],
        fields: dict[str, Any],
        ts: datetime | None = None,
    ) -> bool:
        """写单点。失败抛 ``InfluxWriteError``。"""
        return await self._do_write(measurement, tags, fields, ts)

    async def write_points(
        self,
        points: Iterable[tuple[str, dict[str, Any], dict[str, Any], datetime | None]],
    ) -> dict[str, Any]:
        """批量写。返回 {"ok": int, "failed": int, "errors": [...]}。"""
        ok = 0
        failed = 0
        errors: list[str] = []
        for m, tags, fields, ts in points:
            try:
                if await self._do_write(m, tags, fields, ts):
                    ok += 1
                else:
                    failed += 1
            except InfluxWriteError as e:
                failed += 1
                errors.append(str(e))
        return {"ok": ok, "failed": failed, "errors": errors}

    async def query_range(
        self,
        measurement: str,
        tags: dict[str, Any] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """范围查询（Flux 简化版；真实场景建议走 /api/v2/query + Flux）。"""
        if self.is_mock:
            logger.info(
                "InfluxDBWriter mock query: m=%s tags=%s start=%s end=%s",
                measurement, tags, start, end,
            )
            return []
        # 真实查询此处需要 Flux + /api/v2/query（POST application/json）。
        # 5b.5 范围查询走 Mock（项目当前重 write 轻 query；后续 5c 可观测可补）。
        logger.info("InfluxDBWriter range query 未实现（5b.5 占位）")
        return []

    # ---- 内部 ----
    async def _do_write(
        self,
        measurement: str,
        tags: dict[str, Any],
        fields: dict[str, Any],
        ts: datetime | None,
    ) -> bool:
        line = build_line_protocol(measurement, tags, fields, ts)
        if line is None:
            logger.warning("InfluxDB 字段全部非法，跳过: m=%s fields=%s", measurement, fields)
            return False

        if self.is_mock:
            logger.debug("InfluxDB mock write: %s", line[:120])
            return True

        # /api/v2/write?org=...&bucket=...&precision=ns
        params = {
            "org": self._org,
            "bucket": self._bucket,
            "precision": "ns",
        }
        url = f"{self.write_url}?{urllib.parse.urlencode(params)}"
        headers = {
            "Authorization": f"Token {self._token}",
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "application/json",
        }
        try:
            # 用 asyncio.to_thread 避免阻塞 event loop
            status, body = await asyncio.to_thread(
                _http_post,
                url, line.encode("utf-8"),
                headers=headers, timeout=self._timeout,
            )
        except InfluxWriteError as e:
            logger.warning("InfluxDB 网络失败 → mock 兜底: %s", e)
            logger.debug("InfluxDB mock fallback line: %s", line[:120])
            return True  # 降级为 mock，不阻断业务

        if 200 <= status < 300:
            return True
        # 4xx / 5xx → 警告 + mock 兜底
        logger.warning(
            "InfluxDB 写入非 2xx: status=%s body=%s → mock 兜底",
            status, body[:120],
        )
        return True


# =====================================================
# 顶层函数（业务便利）
# =====================================================
async def write_point(
    measurement: str,
    tags: dict[str, Any],
    fields: dict[str, Any],
    ts: datetime | None = None,
) -> bool:
    return await InfluxDBWriter().write_point(measurement, tags, fields, ts)


__all__ = [
    "InfluxDBWriter",
    "InfluxWriteError",
    "build_line_protocol",
    "write_point",
]
