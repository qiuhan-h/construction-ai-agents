"""集成测试：6b.2 ABAC 引擎 + 字段脱敏 + 租户 SQL 中间件。

覆盖 TR-6.1 ~ TR-6.7：
- TR-6.1: ABAC 时间窗 — 非 9:00-18:00 → evaluate False
- TR-6.2: ABAC 敏感度 — sensitivity=high + clearance=low → False
- TR-6.3: ABAC 超时 — sleep(0.06) 后超时 → False
- TR-6.4: FieldMasker — viewer mask 隐藏 budget
- TR-6.5: FieldMasker — admin mask 不改动
- TR-6.6: tenant_middleware — SELECT 无 tenant_id → 注入 WHERE tenant_id = ?
- TR-6.7: AuthContext 含 role 字段，从 JWT role claim 解析
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.security.abac_engine import ABACEngine, reset_abac_engine
from core.security.field_masking import FieldMasker
from core.security.policies import get_policy_engine, reset_policy_engine
from core.storage.tenant_middleware import (
    TenantContext,
    TenantMiddleware,
    reset_tenant_middleware,
)


@pytest.fixture(autouse=True)
def reset_all():
    reset_abac_engine()
    reset_policy_engine()
    reset_tenant_middleware()
    TenantContext.clear()
    yield
    reset_abac_engine()
    reset_policy_engine()
    reset_tenant_middleware()
    TenantContext.clear()


# =====================================================
# TR-6.1: ABAC 时间窗
# =====================================================
def test_abac_time_window_outside_work_hours_denied() -> None:
    """非工作时段（如 03:00 UTC+8）→ evaluate 返回 False。"""
    engine = ABACEngine()
    # 03:00 UTC+8 → UTC 19:00 前一天
    fake_midnight = datetime(2026, 9, 4, 19, 0, 0, tzinfo=UTC)
    result = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        action="read",
        env_attrs={"now": fake_midnight},
    )
    assert result is False, "非工作时段应被拒绝"


def test_abac_time_window_inside_work_hours_allowed() -> None:
    """工作时段（如 10:00 UTC+8 = 02:00 UTC）→ evaluate 返回 True。"""
    engine = ABACEngine()
    fake_work_hour = datetime(2026, 9, 4, 2, 0, 0, tzinfo=UTC)  # 10:00 UTC+8
    result = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        action="read",
        env_attrs={"now": fake_work_hour},
    )
    assert result is True, "工作时段应被允许"


def test_abac_time_window_disabled_flag() -> None:
    """time_window_enabled=False → 时间窗规则关闭。"""
    engine = ABACEngine()
    fake_midnight = datetime(2026, 9, 4, 19, 0, 0, tzinfo=UTC)
    result = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        action="read",
        env_attrs={"now": fake_midnight, "time_window_enabled": False},
    )
    assert result is True


# =====================================================
# TR-6.2: ABAC 敏感度
# =====================================================
def test_abac_sensitivity_low_clearance_high_sensitivity_denied() -> None:
    """resource.sensitivity=high + subject.clearance=low → False。"""
    engine = ABACEngine()
    fake_work_hour = datetime(2026, 9, 4, 2, 0, 0, tzinfo=UTC)
    result = engine.evaluate(
        subject_attrs={"role": "engineer", "tenant_id": "t1", "clearance": "low"},
        resource_attrs={"tenant_id": "t1", "sensitivity": "high"},
        action="read",
        env_attrs={"now": fake_work_hour},
    )
    assert result is False, "低 clearance 访问 high sensitivity 应被拒绝"


def test_abac_sensitivity_high_clearance_high_sensitivity_allowed() -> None:
    """resource.sensitivity=high + subject.clearance=high → True。"""
    engine = ABACEngine()
    fake_work_hour = datetime(2026, 9, 4, 2, 0, 0, tzinfo=UTC)
    result = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1", "sensitivity": "high"},
        action="read",
        env_attrs={"now": fake_work_hour},
    )
    assert result is True


# =====================================================
# TR-6.3: ABAC 超时
# =====================================================
class _FakeClock:
    """受控单调时钟：手动推进，消除真实 sleep 的时序 flaky（K1 修复）。"""

    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt


def test_abac_timeout_denied() -> None:
    """评估超时（>50ms）→ False。用受控时钟确定性模拟慢规则。"""
    clock = _FakeClock()
    engine = ABACEngine(clock=clock)

    # 注册一个慢规则：执行耗时 0.06s > 0.05s 超时（推进受控时钟，不真实 sleep）
    def slow_rule(subject, resource, action, env):
        clock.advance(0.06)
        return True

    engine.register_rule("slow_rule", slow_rule, description="模拟慢评估")

    fake_work_hour = datetime(2026, 9, 4, 2, 0, 0, tzinfo=UTC)
    result = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        action="read",
        env_attrs={"now": fake_work_hour},
    )
    assert result is False, "评估超时应被拒绝"


def test_abac_timeout_not_triggered_when_rules_fast() -> None:
    """受控时钟不推进（规则瞬时完成）→ 不触发超时，正常评估。"""
    clock = _FakeClock()
    engine = ABACEngine(clock=clock)

    fake_work_hour = datetime(2026, 9, 4, 2, 0, 0, tzinfo=UTC)
    result = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        action="read",
        env_attrs={"now": fake_work_hour},
    )
    assert result is True, "无慢规则且时钟未推进不应触发超时"


# =====================================================
# TR-6.4: FieldMasker — viewer 隐藏 budget
# =====================================================
def test_field_masker_viewer_hides_budget() -> None:
    """viewer 角色 mask({"budget": 1000000, "name": "x"}) → {"name": "x"}。"""
    masker = FieldMasker()
    data = {"budget": 1000000, "name": "x"}
    result = masker.mask(data, "viewer")
    assert "budget" not in result, "viewer 不应看到 budget 字段"
    assert result["name"] == "x"


def test_field_masker_viewer_masks_phone() -> None:
    """viewer 角色 phone → partial 掩码。"""
    masker = FieldMasker()
    data = {"phone": "13812345678", "name": "test"}
    result = masker.mask(data, "viewer")
    assert result["phone"] != "13812345678"
    assert result["phone"].startswith("13")
    assert result["phone"].endswith("78")


def test_field_masker_viewer_masks_contractor() -> None:
    """viewer 角色 contractor → 全掩码 ***。"""
    masker = FieldMasker()
    data = {"contractor": "中建一局", "name": "project"}
    result = masker.mask(data, "viewer")
    assert result["contractor"] == "***"


# =====================================================
# TR-6.5: FieldMasker — admin 不脱敏
# =====================================================
def test_field_masker_admin_no_change() -> None:
    """admin 角色 mask 不改动 dict。"""
    masker = FieldMasker()
    data = {"budget": 1000000, "name": "x", "phone": "13812345678"}
    result = masker.mask(data, "admin")
    assert result == data
    assert result is not data  # 深拷贝，不修改原对象


def test_field_masker_engineer_masks_budget() -> None:
    """engineer 角色 budget → 全掩码 ***（非 hide）。"""
    masker = FieldMasker()
    data = {"budget": 1000000, "name": "x"}
    result = masker.mask(data, "engineer")
    assert "budget" in result  # engineer 是 mask 不是 hide → key 保留
    assert result["budget"] == "***"
    assert result["name"] == "x"


def test_field_masker_nested_dict() -> None:
    """嵌套 dict 递归脱敏。"""
    masker = FieldMasker()
    data = {
        "project_name": "测试项目",
        "budget": 500000,
        "sub": {"budget": 200000, "phone": "13900000000"},
    }
    result = masker.mask(data, "viewer")
    assert "budget" not in result
    assert "budget" not in result["sub"]
    assert result["sub"]["phone"] != "13900000000"
    assert result["project_name"] == "测试项目"


# =====================================================
# TR-6.6: tenant_middleware — SQL 自动注入
# =====================================================
def test_tenant_middleware_injects_where() -> None:
    """SELECT projects 无 tenant_id 条件 → 注入 WHERE tenant_id = :_tenant_id。"""
    mw = TenantMiddleware()
    TenantContext.set_tenant_id("tnt_test123")
    sql = "SELECT * FROM projects"
    new_sql, params = mw.intercept_sql(sql, {})
    assert "tenant_id" in new_sql.lower(), "注入后 SQL 应含 tenant_id"
    assert params.get("_tenant_id") == "tnt_test123"


def test_tenant_middleware_skips_if_already_has_tenant_id() -> None:
    """已有 tenant_id 条件 → 不重复注入。"""
    mw = TenantMiddleware()
    TenantContext.set_tenant_id("tnt_test123")
    sql = "SELECT * FROM projects WHERE tenant_id = 'tnt_old'"
    new_sql, params = mw.intercept_sql(sql, {})
    assert new_sql == sql  # 未修改
    assert "_tenant_id" not in params  # 未追加参数


def test_tenant_middleware_skips_non_select() -> None:
    """非 SELECT → 不注入。"""
    mw = TenantMiddleware()
    TenantContext.set_tenant_id("tnt_test123")
    sql = "INSERT INTO projects (name) VALUES ('test')"
    new_sql, params = mw.intercept_sql(sql, {})
    assert new_sql == sql
    assert "_tenant_id" not in params


def test_tenant_middleware_skips_no_tenant_context() -> None:
    """无 tenant_id 上下文 → 不注入。"""
    mw = TenantMiddleware()
    TenantContext.clear()
    sql = "SELECT * FROM projects"
    new_sql, params = mw.intercept_sql(sql, {})
    assert new_sql == sql


def test_tenant_middleware_injects_and_with_existing_where() -> None:
    """已有 WHERE → 追加 AND tenant_id。"""
    mw = TenantMiddleware()
    TenantContext.set_tenant_id("tnt_test123")
    sql = "SELECT * FROM projects WHERE name = 'test'"
    new_sql, params = mw.intercept_sql(sql, {})
    assert "tenant_id" in new_sql.lower()
    assert params.get("_tenant_id") == "tnt_test123"


def test_tenant_middleware_sqlparse_validation() -> None:
    """TR-6.6: sqlparse 解析注入后 SQL 含 WHERE tenant_id。"""
    try:
        import sqlparse
    except ImportError:
        pytest.skip("sqlparse 未安装")

    mw = TenantMiddleware()
    TenantContext.set_tenant_id("tnt_sqlparse")
    sql = "SELECT * FROM projects"
    new_sql, _ = mw.intercept_sql(sql, {})

    parsed = sqlparse.parse(new_sql)
    assert len(parsed) > 0
    # 验证 SQL 文本含 WHERE tenant_id
    tokens_str = str(parsed[0])
    assert "WHERE" in tokens_str.upper()
    assert "tenant_id" in tokens_str.lower()


# =====================================================
# TR-6.7: AuthContext 含 role 字段
# =====================================================
def test_auth_context_role_from_dev_token() -> None:
    """dev token 解析后 AuthContext.role = admin。"""
    from api.dependencies.auth import _parse_dev_token

    ctx = _parse_dev_token("dev-tnt_test-user1")
    assert ctx.role == "admin"
    assert ctx.tenant_id == "tnt_test"
    assert ctx.user_id == "user1"


def test_auth_context_role_from_jwt_claim() -> None:
    """JWT token 中 role claim → AuthContext.role。"""
    try:
        from jose import jwt
    except ImportError:
        pytest.skip("python-jose 未安装")

    from api.dependencies.auth import _parse_jwt_token
    from config import get_settings

    settings = get_settings()
    secret = settings.api_jwt_secret.get_secret_value()
    payload = {
        "tenant_id": "tnt_jwt",
        "user_id": "user_jwt",
        "role": "engineer",
        "scopes": ["read", "invoke"],
        "attributes": {"clearance": "medium"},
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    ctx = _parse_jwt_token(token)
    assert ctx.role == "engineer"
    assert ctx.tenant_id == "tnt_jwt"
    assert ctx.attributes.get("clearance") == "medium"


def test_auth_context_role_default_viewer_from_jwt() -> None:
    """JWT 无 role claim → AuthContext.role = viewer。"""
    try:
        from jose import jwt
    except ImportError:
        pytest.skip("python-jose 未安装")

    from api.dependencies.auth import _parse_jwt_token
    from config import get_settings

    settings = get_settings()
    secret = settings.api_jwt_secret.get_secret_value()
    payload = {
        "tenant_id": "tnt_default",
        "user_id": "user_default",
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    ctx = _parse_jwt_token(token)
    assert ctx.role == "viewer"


# =====================================================
# PolicyEngine RBAC → ABAC 串联
# =====================================================
def test_policy_engine_rbac_deny_skips_abac() -> None:
    """RBAC 拒绝 → 不走 ABAC（viewer 无 invoke 权限）。"""
    engine = get_policy_engine()
    # viewer 对 safety_audit 无 invoke 权限
    result = engine.evaluate(
        role="viewer",
        resource="safety_audit",
        action="invoke",
        tenant_id="t1",
        subject_attrs={"role": "viewer", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        env_attrs={"time_window_enabled": False},
    )
    assert result is False


def test_policy_engine_rbac_pass_abac_pass() -> None:
    """RBAC 通过 + ABAC 通过 → True。"""
    engine = get_policy_engine()
    fake_work_hour = datetime(2026, 9, 4, 2, 0, 0, tzinfo=UTC)
    result = engine.evaluate(
        role="admin",
        resource="safety_audit",
        action="invoke",
        tenant_id="t1",
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        env_attrs={"now": fake_work_hour},
    )
    assert result is True


def test_policy_engine_rbac_pass_abac_deny() -> None:
    """RBAC 通过 + ABAC 拒绝（敏感度不足）→ False。"""
    engine = get_policy_engine()
    fake_work_hour = datetime(2026, 9, 4, 2, 0, 0, tzinfo=UTC)
    result = engine.evaluate(
        role="engineer",
        resource="safety_audit",
        action="read",
        tenant_id="t1",
        subject_attrs={"role": "engineer", "tenant_id": "t1", "clearance": "low"},
        resource_attrs={"tenant_id": "t1", "sensitivity": "high"},
        env_attrs={"now": fake_work_hour},
    )
    assert result is False
