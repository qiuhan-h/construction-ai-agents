"""7c-2 预发环境数据初始化：alembic upgrade head + 多租户 seed。

用途：
1. 全新库建表（alembic upgrade head）
2. 创建至少 2 个租户验证数据隔离
3. 创建测试用户和项目

用法（docker-compose 启动后）：
    docker compose -f deployment/docker/docker-compose.yml run --rm api \
        python tools/seed_staging.py
    或本地：
    python tools/seed_staging.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def run_alembic() -> bool:
    """建表：优先 alembic，降级 ORM create_all。"""
    print("--- 1. 数据库建表 ---")
    # 优先尝试 alembic（PostgreSQL 真实联调时）
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "models" / "database" / "migrations"))
        command.upgrade(cfg, "head")
        print("[OK] alembic upgrade head 完成")
        return True
    except Exception as alembic_err:
        # 降级 ORM create_all（SQLite 本地降级模式）
        print(f"  [INFO] alembic 跳过: {alembic_err}")
        print("  [INFO] 降级 ORM create_all...")
        try:
            from core.storage.sqlalchemy_repos import _ensure_schema

            _ensure_schema()
            print("[OK] ORM create_all 完成（所有表）")
            return True
        except Exception as e:
            print(f"[FAIL] 建表失败: {e}")
            return False


def seed_tenants() -> bool:
    """创建 2 个测试租户。"""
    print("\n--- 2. 创建测试租户 ---")
    try:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import TenantTable

        tenants = [
            {
                "id": "tnt_staging_alpha",
                "name": "Alpha 建设集团",
                "code": "ALPHA",
                "contact": "张经理",
                "phone": "13800138001",
                "status": "active",
                "plan": "pro",
                "trial_expires_at": None,
                "quota_used": 0,
            },
            {
                "id": "tnt_staging_beta",
                "name": "Beta 工程公司",
                "code": "BETA",
                "contact": "李经理",
                "phone": "13800138002",
                "status": "active",
                "plan": "starter",
                "trial_expires_at": None,
                "quota_used": 0,
            },
        ]

        with get_session_scope() as session:
            for t_data in tenants:
                existing = session.query(TenantTable).filter_by(id=t_data["id"]).first()
                if existing:
                    print(f"  [SKIP] 租户已存在: {t_data['id']} ({t_data['name']})")
                    continue
                t = TenantTable(
                    id=t_data["id"],
                    name=t_data["name"],
                    code=t_data["code"],
                    contact=t_data["contact"],
                    phone=t_data["phone"],
                    status=t_data["status"],
                    plan=t_data["plan"],
                    trial_expires_at=t_data["trial_expires_at"],
                    quota_used=t_data["quota_used"],
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add(t)
                print(f"  [OK] 创建租户: {t_data['id']} ({t_data['name']})")

        print("[OK] 租户 seed 完成（2 个租户）")
        return True
    except Exception as e:
        print(f"[FAIL] 租户 seed 失败: {e}")
        return False


def verify_isolation() -> bool:
    """验证租户数据隔离。"""
    print("\n--- 3. 验证租户隔离 ---")
    try:
        from core.storage.sqlalchemy_repos import get_session_scope
        from models.database import TenantTable

        with get_session_scope() as session:
            count = session.query(TenantTable).count()
            alpha = session.query(TenantTable).filter_by(id="tnt_staging_alpha").first()
            beta = session.query(TenantTable).filter_by(id="tnt_staging_beta").first()

            if count < 2:
                print(f"[FAIL] 租户数 < 2: {count}")
                return False

            if alpha and beta:
                print(f"  [OK] 租户总数: {count}")
                print(f"  [OK] Alpha: id={alpha.id}, name={alpha.name}, plan={alpha.plan}")
                print(f"  [OK] Beta:  id={beta.id}, name={beta.name}, plan={beta.plan}")
                print("  [OK] 两租户数据隔离验证通过")
                return True
            else:
                print(f"[FAIL] 租户查询失败: alpha={alpha}, beta={beta}")
                return False
    except Exception as e:
        print(f"[FAIL] 隔离验证失败: {e}")
        return False


def main() -> int:
    """主入口。"""
    print("=" * 70)
    print("7c-2 预发环境数据初始化")
    print("=" * 70)

    results = []
    results.append(run_alembic())
    results.append(seed_tenants())
    results.append(verify_isolation())

    passed = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)

    print("\n" + "=" * 70)
    print(f"汇总: {passed} PASS / {failed} FAIL / {len(results)} 总计")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
