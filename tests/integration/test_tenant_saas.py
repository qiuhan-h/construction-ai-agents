"""集成测试：6b.1 多租户 SaaS —— 注册 / 配额 429 / 套餐升级 / 租户隔离 / 计费。

覆盖 tasks.md TR-5.1 ~ TR-5.5：
- TR-5.1 注册后 status=trial、quota_used=0、trial_expires_at=now+30d
- TR-5.2 quota_used >= quota_limit 时 check_quota 返回 False
- TR-5.3 upgrade_plan trial→pro 成功后 plan=pro
- TR-5.4 GET /api/v1/tenants/{id} 返回 200 且含 quota 字段
- TR-5.5 trial 租户第 101 次请求返回 429（HTTP 端到端）

测试隔离：每个用例注入全新 InMemoryTenantRepository（不触碰 dev SQLite）。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest

from common.exceptions import (
    QuotaExceededError,
    TenantConflictError,
    TenantSuspendedError,
    ValidationError,
)
from common.timeutils import utc_now
from core.storage.tenant_repo import (
    InMemoryTenantRepository,
    reset_tenant_repository,
    set_tenant_repository_override,
)
from services.billing_service import get_billing_service, reset_billing_service
from services.quota_service import get_quota_service, reset_quota_service
from services.tenant_service import get_tenant_service, reset_tenant_service


# =====================================================
# 隔离 fixture：内存仓储 + 服务单例全重置
# =====================================================
@pytest.fixture(autouse=True)
def isolated_saas():
    set_tenant_repository_override(InMemoryTenantRepository())
    reset_tenant_service()
    reset_quota_service()
    reset_billing_service()
    yield
    set_tenant_repository_override(None)
    reset_tenant_repository()
    reset_tenant_service()
    reset_quota_service()
    reset_billing_service()


def _run(coro):
    return asyncio.run(coro)


def _code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# =====================================================
# 服务层：注册 / 配额
# =====================================================
def test_register_trial_tenant_defaults() -> None:
    """TR-5.1: 新租户 trial / quota=0 / 试用 30 天。"""
    svc = get_tenant_service()
    tenant = _run(svc.register(name="试用单位", code=_code("reg")))

    assert tenant.status.value == "trial"
    assert tenant.plan.value == "trial"
    assert tenant.quota_used["api_calls"] == 0
    assert tenant.quota_used["storage_gb"] == 0
    assert tenant.quota_used["agent_concurrency"] == 0
    assert tenant.trial_expires_at is not None
    delta = tenant.trial_expires_at - utc_now()
    assert timedelta(days=29, hours=23) < delta < timedelta(days=30, minutes=1)
    assert tenant.id.startswith("tnt_")


def test_quota_check_false_and_429_at_limit() -> None:
    """TR-5.2: 达上限后 check_quota=False；继续 consume 抛 QuotaExceededError(429)。"""
    svc = get_tenant_service()
    quota = get_quota_service()
    tenant = _run(svc.register(name="限流单位", code=_code("quota")))

    # 前 100 次放行
    for _ in range(100):
        result = _run(quota.consume(tenant.id, "api_calls", 1))
        assert result["allowed"] is True
    assert result["used"] == 100
    assert result["limit"] == 100
    assert result["remaining"] == 0

    # 第 101 次：check 返回 False
    assert _run(svc.check_quota(tenant.id, "api_calls", 1)) is False

    # consume 直接抛 429
    with pytest.raises(QuotaExceededError) as exc_info:
        _run(quota.consume(tenant.id, "api_calls", 1))
    assert exc_info.value.http_status == 429
    assert exc_info.value.code == "30004"
    assert exc_info.value.details["metric"] == "api_calls"
    assert exc_info.value.details["used"] == 100


def test_upgrade_plan_trial_to_pro() -> None:
    """TR-5.3: trial→pro 后 plan=pro、status=active、额度提升、试用到期清除。"""
    svc = get_tenant_service()
    quota = get_quota_service()
    tenant = _run(svc.register(name="升级单位", code=_code("upg")))

    upgraded = _run(svc.upgrade_plan(tenant.id, "pro"))
    assert upgraded.plan.value == "pro"
    assert upgraded.status.value == "active"
    assert upgraded.trial_expires_at is None

    snap = _run(quota.snapshot(tenant.id))
    assert snap["limit"]["api_calls"] == 100_000
    assert snap["plan"] == "pro"
    # 升级后之前用尽的额度恢复可用
    result = _run(quota.consume(tenant.id, "api_calls", 1))
    assert result["allowed"] is True


def test_upgrade_to_trial_or_unknown_plan_rejected() -> None:
    svc = get_tenant_service()
    tenant = _run(svc.register(name="非法升级", code=_code("badplan")))
    with pytest.raises(ValidationError):
        _run(svc.upgrade_plan(tenant.id, "trial"))
    with pytest.raises(ValidationError):
        _run(svc.upgrade_plan(tenant.id, "platinum"))


def test_trial_expired_blocks_consume() -> None:
    """试用到期 → consume 抛 429（reason=trial_expired）。"""
    svc = get_tenant_service()
    quota = get_quota_service()
    tenant = _run(svc.register(name="到期单位", code=_code("exp")))

    # 手动把试用到期时间改到过去
    svc.repo.update_tenant(
        tenant.id, trial_expires_at=utc_now() - timedelta(days=1)
    )
    with pytest.raises(QuotaExceededError) as exc_info:
        _run(quota.consume(tenant.id, "api_calls", 1))
    assert exc_info.value.http_status == 429
    assert exc_info.value.details.get("reason") == "trial_expired"


def test_suspended_tenant_denied() -> None:
    """停用租户 consume → 403；check_quota → False。"""
    svc = get_tenant_service()
    quota = get_quota_service()
    tenant = _run(svc.register(name="停用单位", code=_code("susp")))

    _run(svc.suspend(tenant.id))
    assert _run(svc.check_quota(tenant.id)) is False
    with pytest.raises(TenantSuspendedError) as exc_info:
        _run(quota.consume(tenant.id, "api_calls", 1))
    assert exc_info.value.http_status == 403


def test_closed_tenant_cannot_upgrade() -> None:
    svc = get_tenant_service()
    tenant = _run(svc.register(name="注销单位", code=_code("close")))
    _run(svc.close(tenant.id))
    with pytest.raises(TenantConflictError):
        _run(svc.upgrade_plan(tenant.id, "pro"))
    # 重复注销也冲突
    with pytest.raises(TenantConflictError):
        _run(svc.close(tenant.id))


def test_concurrency_slot_trial_limit_one() -> None:
    """trial 并发槽位=1：第二次 acquire 429，release 后可再次获取。"""
    svc = get_tenant_service()
    quota = get_quota_service()
    tenant = _run(svc.register(name="并发单位", code=_code("conc")))

    r1 = _run(quota.acquire_slot(tenant.id))
    assert r1["used"] == 1
    with pytest.raises(QuotaExceededError):
        _run(quota.acquire_slot(tenant.id))
    r2 = _run(quota.release_slot(tenant.id))
    assert r2["used"] == 0
    r3 = _run(quota.acquire_slot(tenant.id))
    assert r3["allowed"] is True


def test_tenant_isolation_counters_independent() -> None:
    """A 租户消耗不影响 B 租户配额。"""
    svc = get_tenant_service()
    quota = get_quota_service()
    a = _run(svc.register(name="甲单位", code=_code("iso-a")))
    b = _run(svc.register(name="乙单位", code=_code("iso-b")))

    for _ in range(50):
        _run(quota.consume(a.id, "api_calls", 1))

    snap_a = _run(quota.snapshot(a.id))
    snap_b = _run(quota.snapshot(b.id))
    assert snap_a["used"]["api_calls"] == 50
    assert snap_b["used"]["api_calls"] == 0
    assert snap_a["remaining"]["api_calls"] == 50
    assert snap_b["remaining"]["api_calls"] == 100


def test_duplicate_code_conflict() -> None:
    svc = get_tenant_service()
    code = _code("dup")
    _run(svc.register(name="第一家", code=code))
    with pytest.raises(TenantConflictError) as exc_info:
        _run(svc.register(name="第二家", code=code))
    assert exc_info.value.http_status == 409


# =====================================================
# 服务层：计费（mock 固定月费）
# =====================================================
def test_billing_mock_monthly_fee() -> None:
    svc = get_tenant_service()
    billing = get_billing_service()
    tenant = _run(svc.register(name="计费单位", code=_code("bill")))

    # trial 账单 0 元
    bill_trial = _run(billing.generate_bill(tenant.id, period="2026-09"))
    assert bill_trial.cost == 0.0
    assert bill_trial.plan.value == "trial"

    # 升级 pro 后账单 999
    _run(svc.upgrade_plan(tenant.id, "pro"))
    bill_pro = _run(billing.generate_bill(tenant.id, period="2026-10"))
    assert bill_pro.cost == 999.0
    assert bill_pro.currency == "CNY"
    assert bill_pro.period == "2026-10"

    # 同账期重复出账 → upsert（不产生第二条）
    _run(billing.generate_bill(tenant.id, period="2026-10"))
    bills = _run(billing.list_bills(tenant.id))
    assert len(bills) == 2
    oct_bill = [b for b in bills if b.period == "2026-10"][0]
    assert oct_bill.cost == 999.0


# =====================================================
# API 层端到端（FastAPI TestClient）
# =====================================================
@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c


def _auth(tenant_id: str) -> dict:
    return {"Authorization": f"Bearer dev-{tenant_id}-tester"}


def test_api_register_and_get_with_quota(client) -> None:
    """TR-5.4: 注册 201；GET 200 且含 quota 字段。"""
    resp = client.post(
        "/api/v1/tenants",
        json={"name": "API单位", "code": _code("api-reg")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "0"
    tenant_id = body["data"]["tenant"]["id"]
    assert body["data"]["tenant"]["plan"] == "trial"
    assert body["data"]["tenant"]["status"] == "trial"
    # quota 字段存在
    quota = body["data"]["quota"]
    assert quota["limit"]["api_calls"] == 100
    assert quota["used"]["api_calls"] == 0

    resp_get = client.get(f"/api/v1/tenants/{tenant_id}", headers=_auth(tenant_id))
    assert resp_get.status_code == 200, resp_get.text
    data = resp_get.json()["data"]
    assert "quota" in data
    assert data["tenant"]["id"] == tenant_id
    assert data["quota"]["limit"]["api_calls"] == 100


def test_api_101st_call_returns_429(client) -> None:
    """TR-5.5: trial 租户第 101 次 quota-check 返回 429。"""
    resp = client.post(
        "/api/v1/tenants",
        json={"name": "限流API单位", "code": _code("api-429")},
    )
    tenant_id = resp.json()["data"]["tenant"]["id"]
    headers = _auth(tenant_id)

    statuses = []
    for _ in range(101):
        r = client.post(
            f"/api/v1/tenants/{tenant_id}/quota-check",
            json={},
            headers=headers,
        )
        statuses.append(r.status_code)

    assert statuses[:100] == [200] * 100
    assert statuses[100] == 429
    # 第 101 次响应体为结构化错误
    last = client.post(
        f"/api/v1/tenants/{tenant_id}/quota-check", json={}, headers=headers
    )
    assert last.status_code == 429
    detail = last.json()["detail"]
    assert detail["code"] == "30004"
    assert detail["details"]["metric"] == "api_calls"
    assert detail["details"]["used"] == 100


def test_api_upgrade_plan(client) -> None:
    resp = client.post(
        "/api/v1/tenants",
        json={"name": "升级API单位", "code": _code("api-upg")},
    )
    tenant_id = resp.json()["data"]["tenant"]["id"]
    headers = _auth(tenant_id)

    r = client.post(
        f"/api/v1/tenants/{tenant_id}/upgrade",
        json={"plan": "enterprise"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["tenant"]["plan"] == "enterprise"
    assert data["tenant"]["status"] == "active"
    # enterprise 不限量（-1）
    assert data["quota"]["limit"]["api_calls"] == -1


def test_api_cross_tenant_access_forbidden(client) -> None:
    """B 租户 token 访问 A 租户资源 → 403。"""
    a = client.post(
        "/api/v1/tenants", json={"name": "甲", "code": _code("api-a")}
    ).json()["data"]["tenant"]["id"]
    b = client.post(
        "/api/v1/tenants", json={"name": "乙", "code": _code("api-b")}
    ).json()["data"]["tenant"]["id"]

    r = client.get(f"/api/v1/tenants/{a}", headers=_auth(b))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "30002"
