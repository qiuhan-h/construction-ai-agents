"""ID 生成：ULID（时序可排序）+ 业务前缀。

- 26 位 Crockford Base32：48 位毫秒时间戳 + 80 位随机数，字典序即时间序；
- 统一带业务前缀（如 prj_ / plan_ / alert_），落库与日志中可直接辨识实体类型；
- 无第三方依赖，跨进程/跨节点安全（随机部分来自 os.urandom）。
"""

from __future__ import annotations

import secrets
import time

# Crockford Base32 字母表（去除 I L O U 避免歧义）
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """生成 26 位 ULID 字符串。

    已知限制（设计取舍）：
    - 时间戳取自 ``time.time()``（墙上时钟）。如 NTP 发生回拨，可能产生
      时间戳减小的 ULID，破坏"字典序即时间序"的不变量。生产场景若依赖严格
      单调，应在调用方引入单调时钟或迁移到 ``time.monotonic_ns()``（但跨
      进程不可比，需要外部协调）。
    - 实践经验：受 NTP 微调（slew 模式 ≤500ppm）影响极小；如怀疑回拨，
      可在落库前比对前后 ID 的前 10 字符（时间戳段）。
    """
    timestamp_ms = int(time.time() * 1000)
    entropy = secrets.randbits(80)
    value = (timestamp_ms << 80) | entropy
    return "".join(_ALPHABET[(value >> (5 * i)) & 0x1F] for i in range(25, -1, -1))


def new_id(prefix: str) -> str:
    """生成带业务前缀的 ID，如 prj_01J5ZK..."""
    return f"{prefix}_{new_ulid()}"


# ---------- 业务实体快捷工厂（与 models/domain 一一对应）----------
def tenant_id() -> str:
    return new_id("tnt")


def project_id() -> str:
    return new_id("prj")


def plan_id() -> str:
    return new_id("plan")


def inspection_id() -> str:
    return new_id("insp")


def violation_id() -> str:
    return new_id("vio")


def alert_id() -> str:
    return new_id("alert")


def report_id() -> str:
    return new_id("rpt")


def task_id() -> str:
    return new_id("task")


# ---------- 阶段二新增：法规/标准/案例/事件/消息前缀 ----------
def regulation_id() -> str:
    return new_id("reg")


def standard_id() -> str:
    return new_id("std")


def case_id() -> str:
    return new_id("case")


def event_id() -> str:
    return new_id("evt")


def message_id() -> str:
    return new_id("msg")


# ---------- 阶段五新增：地理围栏/越界事件前缀（5b.3 / 5b.7）----------
def geofence_id() -> str:
    return new_id("fence")


def geofence_violation_id() -> str:
    """越界事件 ID（5b.3 落地于 GeofenceViolationTable）。"""
    return new_id("fvio")
