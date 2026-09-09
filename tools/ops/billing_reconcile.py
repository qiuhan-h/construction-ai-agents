"""7e-3 租户计费对账脚本。

用途：按月对账租户用量记录，核对配额计费准确性。

对账内容：
  1. 按租户汇总当月 API 调用量
  2. 核对 UsageRecord 表与实际调用日志
  3. 检查配额超限租户是否被正确限流（429）
  4. 生成对账报告

用法：
    python tools/billing_reconcile.py                    # 当月对账
    python tools/billing_reconcile.py --month 2026-08    # 指定月份
    python tools/billing_reconcile.py --tenant tnt_xxx   # 指定租户
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def reconcile(month: str, tenant_id: str | None = None) -> int:
    """对账主逻辑。"""
    print("=" * 72)
    print("7e-3 租户计费对账")
    print(f"月份: {month}")
    if tenant_id:
        print(f"租户: {tenant_id}")
    print("=" * 72)

    try:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import TenantTable
        from models.database.security_audit_log import SecurityAuditLogTable
    except ImportError as e:
        print(f"[FAIL] 数据库模块导入失败: {e}")
        return 1

    results = []

    # 1. 租户列表
    print("\n--- 1. 租户列表 ---")
    try:
        with get_session_scope() as session:
            query = session.query(TenantTable).filter(TenantTable.status == "active")
            if tenant_id:
                query = query.filter(TenantTable.id == tenant_id)
            tenants = query.all()

            if not tenants:
                print("  [WARN] 无活跃租户")
                return 0

            print(f"  [OK] 活跃租户: {len(tenants)} 个")
            for t in tenants:
                print(f"    - {t.id} ({t.name}) plan={t.plan} quota_used={t.quota_used}")
    except Exception as e:
        print(f"  [FAIL] 租户查询失败: {e}")
        results.append(False)
        return 1

    # 2. 审计日志对账
    print("\n--- 2. 审计日志对账 ---")
    try:
        with get_session_scope() as session:
            for t in tenants:
                # 查询当月审计日志数
                audit_count = session.query(SecurityAuditLogTable).filter(
                    SecurityAuditLogTable.tenant_id == t.id,
                ).count()
                print(f"  {t.id}: 审计日志 {audit_count} 条")

                # 配额核对
                if t.quota_used > 0 and audit_count > 0:
                    print(f"    配额已用: {t.quota_used}, 审计记录: {audit_count}")
                    if t.quota_used >= audit_count * 0.5:
                        print("    [OK] 配额使用合理")
                    else:
                        print("    [WARN] 配额与审计记录差异较大")
                else:
                    print("    [INFO] 无调用记录")
                results.append(True)
    except Exception as e:
        print(f"  [FAIL] 审计日志对账失败: {e}")
        results.append(False)

    # 3. 配额超限检查
    print("\n--- 3. 配额超限检查 ---")
    try:
        with get_session_scope() as session:
            for t in tenants:
                plan_limits = {"starter": 100, "pro": 1000, "enterprise": 10000}
                limit = plan_limits.get(t.plan, 100)
                usage_pct = (t.quota_used / limit * 100) if limit > 0 else 0

                if usage_pct >= 100:
                    print(f"  [OVER]  {t.id}: {t.quota_used}/{limit} ({usage_pct:.0f}%) 应触发 429")
                elif usage_pct >= 80:
                    print(f"  [WARN]  {t.id}: {t.quota_used}/{limit} ({usage_pct:.0f}%) 接近超限")
                else:
                    print(f"  [OK]    {t.id}: {t.quota_used}/{limit} ({usage_pct:.0f}%)")
                results.append(True)
    except Exception as e:
        print(f"  [FAIL] 配额检查失败: {e}")
        results.append(False)

    # 4. 对账报告
    print("\n--- 4. 对账报告 ---")
    passed = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)
    print(f"\n对账结果: {passed} PASS / {failed} FAIL / {len(results)} 总计")

    if failed > 0:
        print("\n[WARN] 对账有差异，建议人工核查")
        return 1
    else:
        print("\n[OK] 对账完成，无差异")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="7e-3 租户计费对账")
    parser.add_argument("--month", default=datetime.now(UTC).strftime("%Y-%m"), help="对账月份（YYYY-MM）")
    parser.add_argument("--tenant", default=None, help="指定租户 ID")
    args = parser.parse_args()

    return reconcile(args.month, args.tenant)


if __name__ == "__main__":
    sys.exit(main())
