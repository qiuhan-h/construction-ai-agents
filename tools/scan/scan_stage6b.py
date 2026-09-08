"""阶段六·子阶段 6b（多租户 SaaS + ABAC + 字段脱敏 + 租户中间件）目标文件清单。

覆盖：
- 6b.1 租户 + 计费 + 配额（Task 5：domain/ORM/repo/service/router/test）
- 6b.2 ABAC 引擎 + FieldMasker + tenant_middleware + AuthContext role（Task 6）

执行：python scan_stage6b.py
退出码：0 = 全部就位且非空；非 0 = 有缺失/空壳。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"

# 6b 新增文件（必须存在且非空）
STAGE6B_NEW = [
    # 6b.1 租户 + 计费 + 配额（Task 5）
    "models/domain/billing.py",
    "models/database/billing_models.py",
    "core/storage/tenant_repo.py",
    "services/tenant_service.py",
    "services/quota_service.py",
    "services/billing_service.py",
    "api/routers/tenant_router.py",
    "tests/integration/test_tenant_saas.py",
    # 6b.2 ABAC + 脱敏 + 租户中间件（Task 6）
    "core/security/abac_engine.py",
    "core/security/field_masking.py",
    "core/storage/tenant_middleware.py",
    "tests/integration/test_abac_masking_tenant.py",
]

# 6b 改造文件（必须存在且非空；内容由 verify_stage6b 运行期校验）
STAGE6B_MODIFIED = [
    # Task 5 改造
    "common/constants.py",
    "common/error_codes.py",
    "common/exceptions.py",
    "models/database/project_models.py",
    "models/database/__init__.py",
    "models/domain/tenant.py",
    "models/domain/__init__.py",
    "api/routers/__init__.py",
    "api/main.py",
    # Task 6 改造
    "api/dependencies/auth.py",
    "core/security/policies.py",
    "core/security/__init__.py",
]


def main() -> int:
    print(f"{'path':78} {'size':>8}  status")
    print("-" * 96)
    missing = 0
    empty = 0
    ok = 0
    for rel in STAGE6B_NEW + STAGE6B_MODIFIED:
        p = ROOT / rel
        if not p.is_file():
            print(f"{rel:78} {'-':>8}  MISSING")
            missing += 1
            continue
        size = p.stat().st_size
        if size == 0:
            print(f"{rel:78} {size:>8}  EMPTY")
            empty += 1
        else:
            tag = "OK " if rel in STAGE6B_NEW else "OK*"
            print(f"{rel:78} {size:>8}  {tag}")
            ok += 1
    total = len(STAGE6B_NEW) + len(STAGE6B_MODIFIED)
    print("-" * 96)
    print(f"已实现: {ok}   0 字节占位: {empty}   不存在: {missing}   合计: {total}")
    print("(OK  = 6b 新增文件；OK* = 6b 改造文件，运行期行为由 verify_stage6b.py 校验)")
    return 0 if missing == 0 and empty == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
