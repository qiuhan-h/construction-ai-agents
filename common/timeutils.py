"""时间工具：全平台统一使用 UTC 感知时间（timezone-aware）。

约定：
- 领域模型与数据库中的时间一律为 UTC 且带时区信息；
- 展示层（Streamlit/API 响应）负责转为本地时区；
- 禁止使用 datetime.utcnow()（返回 naive 时间）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

UTC = UTC


def utc_now() -> datetime:
    """当前 UTC 时间（带时区）。"""
    return datetime.now(UTC)


def utc_today() -> date:
    """当前 UTC 日期。"""
    return utc_now().date()


def ensure_utc(dt: datetime) -> datetime:
    """归一化为 UTC：naive 时间按 UTC 处理，aware 时间转 UTC。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_iso(dt: datetime) -> str:
    """格式化为 ISO-8601 字符串（UTC，微秒精度）。"""
    return ensure_utc(dt).isoformat()


def from_iso(value: str) -> datetime:
    """解析 ISO-8601 字符串为 UTC aware datetime。"""
    dt = datetime.fromisoformat(value)
    return ensure_utc(dt)


def utc_day_bounds(day: date | datetime) -> tuple[datetime, datetime]:
    """返回指定日期在 UTC 下的 [00:00, 次日 00:00) 区间（用于日报聚合）。"""
    d = day.date() if isinstance(day, datetime) else day
    start = datetime.combine(d, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def add(seconds: float, *, base: datetime | None = None) -> datetime:
    """在 base（默认 now）上增加秒数，返回 UTC aware datetime。"""
    return ensure_utc(base or utc_now()) + timedelta(seconds=seconds)
