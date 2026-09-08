"""法规数据灌入：扫描 data/regulations/*.md → RegulationLoader → ORM upsert + 事件。

设计（4d D7 幂等，5b.3 升级 ORM）：
- 文件名约定：``{code}-{version}.md``，例 ``GB50016-2014.md``；
- 重复执行等价于 upsert：code + version + article 唯一；已存在则覆盖；
- 5b.3：扫描结果写入 ``RegulationRepository``（SQLAlchemy ORM）；
  缺包 / 缺表时降级为只打印（不抛错，保持 4d 接口契约）；
- 注册成功后通过事件总线发布 ``TOPIC_REGULATION_UPDATED``，编排器会触发
  ``regulation_record`` 工作流（仅记录 + 通知）。

用法：
    python scripts/load_regulations.py                       # 默认 data/regulations
    python scripts/load_regulations.py --dir data/regulations
    python scripts/load_regulations.py --tenant tnt_x
    python scripts/load_regulations.py --dry-run
    python scripts/load_regulations.py --list                 # 仅列出当前 loader 缓存

退出码：
    0  成功
    1  目录不存在或扫描失败
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger("scripts.load_regulations")


# =====================================================
# ORM 仓储获取（5b.3 新增）
# =====================================================
def _get_regulation_repo() -> Any:
    """返回 ``RegulationRepository`` 或 None。"""
    try:
        from core.storage.sqlalchemy_repos import (
            BackendUnavailableError,
            get_regulation_repository,
            init_database_for_dev,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("导入 ORM 仓储失败: %s", e)
        return None
    try:
        init_database_for_dev()
        return get_regulation_repository()
    except BackendUnavailableError:
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("ORM 初始化失败: %s", e)
        return None


def _build_loader(data_dir: str) -> Any:
    """构造 RegulationLoader（兼容两种导入路径）。"""
    try:
        from agents.compliance_agent.regulation_engine.mcp_loader import (
            RegulationLoader,
        )
        return RegulationLoader(data_dir=data_dir)
    except Exception as e:  # noqa: BLE001
        logger.debug("regulation_engine.mcp_loader 不可用: %s", e)
    from agents.compliance_agent.regulation_engine.mcp_loader import (
        RegulationLoader as _RL,
    )
    return _RL(data_dir=data_dir)


async def _publish_regulation_updated(
    code: str, version: str, action: str = "loaded"
) -> None:
    """发布 regulation.updated 事件（fire-and-forget）。"""
    try:
        from core.events import publish, TOPIC_REGULATION_UPDATED
    except Exception as e:  # noqa: BLE001
        logger.debug("event_bus 不可用（跳过事件）: %s", e)
        return
    try:
        await publish(
            topic=TOPIC_REGULATION_UPDATED,
            tenant_id="tnt_system",
            source="scripts.load_regulations",
            code=code,
            version=version,
            action=action,
        )
        logger.debug(
            "已发布事件: %s code=%s v=%s", TOPIC_REGULATION_UPDATED, code, version
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("发布事件失败（不影响数据加载）: %s", e)


def _to_orm_records(
    items: list[dict[str, Any]], tenant_id: str
) -> list[dict[str, Any]]:
    """将 loader 扫描结果转成 ORM ``RegulationRepository.add`` 可接受 dict。"""
    out: list[dict[str, Any]] = []
    for r in items:
        out.append(
            {
                "tenant_id": tenant_id,
                "code": str(r.get("code", "")),
                "version": str(r.get("version", "")),
                "article": r.get("article"),
                "title": r.get("name") or r.get("title") or f"{r.get('code')}-{r.get('version')}",
                "chapter": r.get("chapter"),
                "content": r.get("content") or r.get("text") or "",
                "keywords": list(r.get("keywords") or r.get("categories") or []),
                "related_regulations": list(r.get("related_regulations") or []),
            }
        )
    return out


async def async_main(args: argparse.Namespace) -> int:
    project_root = _PROJECT_ROOT
    data_dir = (
        args.dir
        if os.path.isabs(args.dir)
        else os.path.join(project_root, args.dir)
    )
    if not os.path.isdir(data_dir):
        print(f"法规目录不存在: {data_dir}", file=sys.stderr)
        return 1

    loader = _build_loader(data_dir)
    if args.list:
        items = loader.list_all()
        print(f"当前法规缓存数: {len(items)}")
        for r in items:
            print(
                f"  - {r['code']}-{r['version']}  name={r.get('name', '')!s}  "
                f"cats={r.get('categories')}"
            )
        return 0

    if args.dry_run:
        logger.info("DRY-RUN 模式：只扫描不写")
    # bootstrap 实际读取 + 解析
    items = loader.bootstrap()
    if not items:
        # 命名约定：{code}-{version}.md；此处 code/version 是字面占位
        print(
            f"目录 {data_dir} 未发现合法法规文件"
            f"（命名格式：<code>-<version>.md，例 GB50016-2014.md）"
        )
        return 0

    print(f"扫描 {data_dir} → 法规数 {len(items)}")
    for r in items:
        print(
            f"  - {r['code']}-{r['version']}  categories={r.get('categories')}  "
            f"name={r.get('name', '')}"
        )

    if args.dry_run:
        return 0

    # 5b.3：ORM upsert（缺包时降级为只打印）
    n_orm = 0
    repo = _get_regulation_repo()
    if repo is not None:
        for rec in _to_orm_records(items, args.tenant):
            try:
                repo.add(rec)
                n_orm += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("ORM 法规写入失败: %s", e)
        print(f"\n✓ ORM upsert {n_orm} 法规")
    else:
        print("\n⚠️ ORM 不可用，跳过 DB 写入（仅发事件）")

    # 触发事件（编排器会做记录 + 通知）
    for r in items:
        await _publish_regulation_updated(
            code=r["code"], version=str(r["version"]), action="loaded"
        )
        # 留间隔避免瞬时尖峰
        await asyncio.sleep(0.01)

    print()
    print("=" * 60)
    print(
        f"法规加载完成: 目录={data_dir} 数量={len(items)} "
        f"orm_writes={n_orm} tenant={args.tenant}"
    )
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="阶段 4d / 5b.3：法规数据灌入")
    parser.add_argument(
        "--dir",
        default="data/regulations",
        help="法规目录（默认 data/regulations）",
    )
    parser.add_argument("--tenant", default="tnt_system", help="事件 tenant_id（默认 tnt_system）")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不触发事件")
    parser.add_argument("--list", action="store_true", help="只列出当前缓存")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出扫描结果")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    rc = asyncio.run(async_main(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
