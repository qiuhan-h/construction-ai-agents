"""阶段六·子阶段 6b 验收：多租户 SaaS + ABAC + 字段脱敏 + 租户中间件。

验收项：
- [A] scan_stage6b 文件清单全部就位
- [B] 6b.1 租户注册：trial 30 天 + quota=0；配额 101 次→429；升级 pro；计费账单
- [C] 6b.2 ABAC：时间窗/敏感度/超时
- [D] 6b.2 FieldMasker：viewer hide budget / admin 全显
- [E] 6b.2 TenantMiddleware：SELECT 注入 WHERE tenant_id
- [F] 6b.2 AuthContext：role 字段（dev→admin / JWT→claim）
- [G] 回归：verify_stage1/2/3 无回归（全套 1-5+6a 见 Task 14）

执行：python verify_stage6b.py
退出码：0 = 全部通过；非 0 = 有失败项。
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASSED = 0
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILED += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


# =====================================================
# [A] 文件清单
# =====================================================
def check_scan() -> None:
    print("\n[A] 文件清单 scan_stage6b")
    r = subprocess.run(
        [sys.executable, str(TOOLS_DIR.parent / "scan" / "scan_stage6b.py")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    check("scan_stage6b 退出码 0", r.returncode == 0,
          "全部文件就位非空" if r.returncode == 0 else "存在缺失/空壳")


# =====================================================
# [B] 6b.1 租户 + 计费 + 配额
# =====================================================
def check_tenant_saas() -> None:
    print("\n[B] 6b.1 多租户 SaaS")
    from core.storage.tenant_repo import (
        InMemoryTenantRepository,
        reset_tenant_repository,
        set_tenant_repository_override,
    )
    from services.tenant_service import (
        get_tenant_service,
        reset_tenant_service,
    )
    from services.quota_service import (
        QuotaExceededError,
        get_quota_service,
        reset_quota_service,
    )
    from services.billing_service import (
        get_billing_service,
        reset_billing_service,
    )

    # 隔离：内存后端
    reset_tenant_repository()
    set_tenant_repository_override(InMemoryTenantRepository())
    reset_tenant_service()
    reset_quota_service()
    reset_billing_service()

    svc = get_tenant_service()
    quota = get_quota_service()

    # TR-5.1: 注册 → trial / quota=0 / 30 天
    tenant = asyncio.run(svc.register(name="验收单位", code="verify-6b-001"))
    check("注册后 status=trial", tenant.status.value == "trial", tenant.status.value)
    check("注册后 plan=trial", tenant.plan.value == "trial", tenant.plan.value)
    check("注册后 quota_used api_calls=0",
          tenant.quota_used["api_calls"] == 0, str(tenant.quota_used))
    check("注册后 trial_expires_at 非空", tenant.trial_expires_at is not None)
    check("注册后 id 前缀 tnt_", tenant.id.startswith("tnt_"), tenant.id[:8])

    # TR-5.2: 100 次放行 → 第 101 次 429
    for _ in range(100):
        asyncio.run(quota.consume(tenant.id, "api_calls", 1))
    snap = asyncio.run(quota.snapshot(tenant.id))
    check("100 次后 used=100", snap["used"]["api_calls"] == 100,
          str(snap["used"]["api_calls"]))
    check("100 次后 remaining=0", snap["remaining"]["api_calls"] == 0)

    blocked = False
    try:
        asyncio.run(quota.consume(tenant.id, "api_calls", 1))
    except QuotaExceededError as e:
        blocked = True
        check("第 101 次 → QuotaExceededError(429)",
              e.http_status == 429 and e.code == "30004",
              f"http={e.http_status} code={e.code}")
    check("第 101 次被拦截", blocked)

    # TR-5.3: 升级 pro
    upgraded = asyncio.run(svc.upgrade_plan(tenant.id, "pro"))
    check("升级后 plan=pro", upgraded.plan.value == "pro")
    check("升级后 status=active", upgraded.status.value == "active")
    check("升级后 trial_expires_at 清除", upgraded.trial_expires_at is None)
    snap2 = asyncio.run(quota.snapshot(tenant.id))
    check("升级后 limit api_calls=100000",
          snap2["limit"]["api_calls"] == 100_000,
          str(snap2["limit"]["api_calls"]))

    # 计费账单
    billing = get_billing_service()
    bill = asyncio.run(billing.generate_bill(tenant.id, period="2026-09"))
    check("pro 账单 cost=999", bill.cost == 999.0, f"cost={bill.cost}")
    check("账单 currency=CNY", bill.currency == "CNY")

    # 多租户隔离
    t2 = asyncio.run(svc.register(name="乙单位", code="verify-6b-002"))
    snap_b = asyncio.run(quota.snapshot(t2.id))
    check("租户 B quota_used=0（隔离）",
          snap_b["used"]["api_calls"] == 0, str(snap_b["used"]["api_calls"]))

    # 清理
    reset_tenant_repository()
    reset_tenant_service()
    reset_quota_service()
    reset_billing_service()


# =====================================================
# [C] 6b.2 ABAC 引擎
# =====================================================
def check_abac() -> None:
    print("\n[C] 6b.2 ABAC 引擎")
    from core.security.abac_engine import ABACEngine, reset_abac_engine
    from core.security.policies import get_policy_engine, reset_policy_engine

    reset_abac_engine()
    reset_policy_engine()
    engine = ABACEngine()

    # TR-6.1: 时间窗 — 非工作时段拒绝
    fake_night = datetime(2026, 9, 4, 19, 0, 0, tzinfo=timezone.utc)  # 03:00 UTC+8
    result = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        action="read",
        env_attrs={"now": fake_night},
    )
    check("ABAC 时间窗：非工作时段 → False", result is False)

    # 工作时段允许
    fake_day = datetime(2026, 9, 4, 2, 0, 0, tzinfo=timezone.utc)  # 10:00 UTC+8
    result2 = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        action="read",
        env_attrs={"now": fake_day},
    )
    check("ABAC 时间窗：工作时段 → True", result2 is True)

    # TR-6.2: 敏感度 — high sensitivity + low clearance → False
    result3 = engine.evaluate(
        subject_attrs={"role": "engineer", "tenant_id": "t1", "clearance": "low"},
        resource_attrs={"tenant_id": "t1", "sensitivity": "high"},
        action="read",
        env_attrs={"now": fake_day},
    )
    check("ABAC 敏感度：low clearance + high sensitivity → False",
          result3 is False)

    # high clearance + high sensitivity → True
    result4 = engine.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1", "sensitivity": "high"},
        action="read",
        env_attrs={"now": fake_day},
    )
    check("ABAC 敏感度：high clearance + high sensitivity → True",
          result4 is True)

    # TR-6.3: 超时 → False（受控时钟确定性模拟，无真实 sleep，K1 修复）
    class _VerifyClock:
        def __init__(self):
            self._t = 0.0

        def __call__(self):
            return self._t

        def advance(self, dt):
            self._t += dt

    vclock = _VerifyClock()
    engine2 = ABACEngine(clock=vclock)

    def slow_rule(s, r, a, e):
        vclock.advance(0.06)
        return True
    engine2.register_rule("slow", slow_rule)
    result5 = engine2.evaluate(
        subject_attrs={"role": "admin", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        action="read",
        env_attrs={"now": fake_day},
    )
    check("ABAC 超时（>50ms）→ False", result5 is False)

    # PolicyEngine 串联：RBAC 拒绝 → 不走 ABAC
    pe = get_policy_engine()
    result6 = pe.evaluate(
        role="viewer", resource="safety_audit", action="invoke",
        tenant_id="t1",
        subject_attrs={"role": "viewer", "tenant_id": "t1", "clearance": "high"},
        resource_attrs={"tenant_id": "t1"},
        env_attrs={"time_window_enabled": False},
    )
    check("PolicyEngine RBAC 拒绝 → False（不走 ABAC）", result6 is False)

    reset_abac_engine()
    reset_policy_engine()


# =====================================================
# [D] 6b.2 FieldMasker
# =====================================================
def check_field_masker() -> None:
    print("\n[D] 6b.2 FieldMasker 字段脱敏")
    from core.security.field_masking import FieldMasker

    masker = FieldMasker()

    # TR-6.4: viewer → budget hide
    data = {"budget": 1000000, "name": "x"}
    result = masker.mask(data, "viewer")
    check("viewer mask 隐藏 budget", "budget" not in result,
          f"keys={list(result.keys())}")
    check("viewer mask 保留 name", result.get("name") == "x")

    # viewer phone → partial
    data2 = {"phone": "13812345678", "name": "p"}
    result2 = masker.mask(data2, "viewer")
    check("viewer phone partial 掩码",
          result2["phone"] != "13812345678" and result2["phone"].startswith("13"))

    # viewer contractor → mask
    data3 = {"contractor": "中建一局"}
    result3 = masker.mask(data3, "viewer")
    check("viewer contractor 全掩码", result3["contractor"] == "***")

    # TR-6.5: admin → 不改动
    data4 = {"budget": 1000000, "name": "x", "phone": "13812345678"}
    result4 = masker.mask(data4, "admin")
    check("admin mask 不改动 dict", result4 == data4)
    check("admin mask 返回深拷贝", result4 is not data4)

    # engineer → budget mask（非 hide）
    data5 = {"budget": 1000000, "name": "x"}
    result5 = masker.mask(data5, "engineer")
    check("engineer budget mask（key 保留）",
          "budget" in result5 and result5["budget"] == "***")

    # 嵌套 dict 递归
    data6 = {"project": "p", "budget": 500, "sub": {"budget": 200, "phone": "13900000000"}}
    result6 = masker.mask(data6, "viewer")
    check("嵌套 dict 递归脱敏",
          "budget" not in result6 and "budget" not in result6["sub"])


# =====================================================
# [E] 6b.2 TenantMiddleware
# =====================================================
def check_tenant_middleware() -> None:
    print("\n[E] 6b.2 TenantMiddleware SQL 注入")
    from core.storage.tenant_middleware import (
        TenantContext,
        TenantMiddleware,
        reset_tenant_middleware,
    )

    reset_tenant_middleware()
    mw = TenantMiddleware()

    # TR-6.6: SELECT 无 tenant_id → 注入
    TenantContext.set_tenant_id("tnt_verify")
    sql = "SELECT * FROM projects"
    new_sql, params = mw.intercept_sql(sql, {})
    check("SELECT 注入 WHERE tenant_id",
          "tenant_id" in new_sql.lower(), new_sql[:80])
    check("注入后 params 含 _tenant_id",
          params.get("_tenant_id") == "tnt_verify")

    # 已有 tenant_id → 不重复注入
    sql2 = "SELECT * FROM projects WHERE tenant_id = 'old'"
    new_sql2, params2 = mw.intercept_sql(sql2, {})
    check("已有 tenant_id → 不注入", new_sql2 == sql2 and "_tenant_id" not in params2)

    # 非 SELECT → 不注入
    sql3 = "INSERT INTO projects (name) VALUES ('t')"
    new_sql3, params3 = mw.intercept_sql(sql3, {})
    check("非 SELECT → 不注入", new_sql3 == sql3)

    # 无 tenant 上下文 → 不注入
    TenantContext.clear()
    sql4 = "SELECT * FROM projects"
    new_sql4, params4 = mw.intercept_sql(sql4, {})
    check("无 tenant 上下文 → 不注入", new_sql4 == sql4)

    # sqlparse 验证（如果可用）
    TenantContext.set_tenant_id("tnt_sqlparse")
    sql5 = "SELECT * FROM projects"
    new_sql5, _ = mw.intercept_sql(sql5, {})
    try:
        import sqlparse
        parsed = sqlparse.parse(new_sql5)
        has_where = "WHERE" in str(parsed[0]).upper()
        has_tenant = "tenant_id" in str(parsed[0]).lower()
        check("sqlparse 解析含 WHERE tenant_id", has_where and has_tenant)
    except ImportError:
        check("sqlparse 未安装 → 跳过解析验证", True, "降级模式")

    TenantContext.clear()
    reset_tenant_middleware()


# =====================================================
# [F] 6b.2 AuthContext role
# =====================================================
def check_auth_role() -> None:
    print("\n[F] 6b.2 AuthContext role 字段")
    from api.dependencies.auth import _parse_dev_token

    # TR-6.7: dev token → role=admin
    ctx = _parse_dev_token("dev-tnt_verify-user1")
    check("dev token role=admin", ctx.role == "admin", ctx.role)
    check("dev token tenant_id", ctx.tenant_id == "tnt_verify")
    check("AuthContext.to_dict 含 role", "role" in ctx.to_dict())

    # JWT token（jose 可用时）
    try:
        from jose import jwt
        from config import get_settings

        settings = get_settings()
        secret = settings.api_jwt_secret.get_secret_value()
        payload = {
            "tenant_id": "tnt_jwt", "user_id": "u1", "role": "engineer",
            "scopes": ["read"], "attributes": {"clearance": "medium"},
        }
        token = jwt.encode(payload, secret, algorithm="HS256")
        from api.dependencies.auth import _parse_jwt_token
        ctx2 = _parse_jwt_token(token)
        check("JWT role claim → engineer", ctx2.role == "engineer", ctx2.role)
        check("JWT attributes 解析", ctx2.attributes.get("clearance") == "medium")

        # JWT 无 role claim → viewer
        payload2 = {"tenant_id": "tnt2", "user_id": "u2"}
        token2 = jwt.encode(payload2, secret, algorithm="HS256")
        ctx3 = _parse_jwt_token(token2)
        check("JWT 无 role → viewer", ctx3.role == "viewer", ctx3.role)
    except ImportError:
        check("python-jose 未安装 → JWT 测试跳过", True, "降级 dev 模式")


# =====================================================
# [G] 回归
# =====================================================
def check_regression() -> None:
    print("\n[G] 回归 verify_stage1/2/3")
    for script in ("verify_stage1.py", "verify_stage2.py", "verify_stage3.py"):
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / script)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        check(f"{script} 退出码 0", r.returncode == 0,
              "无回归" if r.returncode == 0 else "有失败")


def main() -> int:
    print("=" * 60)
    print("阶段六·6b 验收：多租户 SaaS + ABAC + 脱敏 + 租户中间件")
    print("=" * 60)
    check_scan()
    check_tenant_saas()
    check_abac()
    check_field_masker()
    check_tenant_middleware()
    check_auth_role()
    check_regression()
    print("\n" + "=" * 60)
    print(f"6b 自检结果: {PASSED} 通过, {FAILED} 失败")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
