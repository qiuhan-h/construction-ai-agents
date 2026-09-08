"""向量库初始化：InMemoryVectorStore 灌入法规 + 案例文本。

设计（4d D7 幂等）：
- 默认从 ``data/regulations/*.md`` + ``data/cases/*.md`` 读取纯文本；
- 复用 ``safety_audit_agent.knowledge_base.vector_store.InMemoryVectorStore``；
- 重复执行等价于 upsert：record id 由 ``code/version/case_id`` 决定；
- 4d 阶段用 ``InMemoryVectorStore``；阶段五切换 ChromaDB 时
  只需替换 ``_make_store()`` 实现。

用法：
    python scripts/setup_vector_db.py
    python scripts/setup_vector_db.py --reg-dir data/regulations
    python scripts/setup_vector_db.py --case-dir data/cases
    python scripts/setup_vector_db.py --tenant tnt_demo
    python scripts/setup_vector_db.py --dry-run
    python scripts/setup_vector_db.py --stats          # 打印当前 store count

退出码：
    0  成功
    1  目录不存在
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from typing import Any

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger("scripts.setup_vector_db")


# 法规文件命名：GB50016-2014.md
_REG_FILENAME_RE = re.compile(r"^([A-Z]+\d+(?:[-/][A-Z0-9]+)?)-(\d{4})\.md$")
# 案例文件命名：case_001.md / CASE-2024-001.md
_CASE_FILENAME_RE = re.compile(r"^[Cc]ase[-_]?([A-Za-z0-9_-]+)\.md$")


# =====================================================
# 工具
# =====================================================
def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _truncate(text: str, max_len: int = 4000) -> str:
    """向量库首版只索引前 N 字符（避免大文件把 token 撑爆）。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n…[truncated]"


def _make_store() -> Any:
    """构造向量库（4d：InMemory；阶段五：ChromaDB）。"""
    try:
        from agents.safety_audit_agent.knowledge_base.vector_store import (
            InMemoryVectorStore,
            VectorRecord,
        )
        return InMemoryVectorStore(), VectorRecord
    except Exception as e:  # noqa: BLE001
        logger.error("导入 InMemoryVectorStore 失败: %s", e)
        raise


# =====================================================
# 扫描
# =====================================================
def _scan_regulations(reg_dir: str, tenant_id: str) -> list[dict[str, Any]]:
    """扫描法规目录，返回待索引记录（不调用 store）。"""
    out: list[dict[str, Any]] = []
    if not os.path.isdir(reg_dir):
        return out
    for name in sorted(os.listdir(reg_dir)):
        if not name.endswith(".md"):
            continue
        m = _REG_FILENAME_RE.match(name)
        if not m:
            logger.debug("跳过非法命名法规: %s", name)
            continue
        code, version = m.group(1), m.group(2)
        path = os.path.join(reg_dir, name)
        try:
            text = _read_text(path)
        except OSError as e:
            logger.warning("读取法规失败 %s: %s", path, e)
            continue
        out.append(
            {
                "id": f"reg:{code}:{version}",
                "tenant_id": tenant_id,
                "text": _truncate(text),
                "metadata": {
                    "kind": "regulation",
                    "code": code,
                    "version": version,
                    "source": path,
                },
            }
        )
    return out


def _scan_cases(case_dir: str, tenant_id: str) -> list[dict[str, Any]]:
    """扫描案例目录。"""
    out: list[dict[str, Any]] = []
    if not os.path.isdir(case_dir):
        return out
    for name in sorted(os.listdir(case_dir)):
        if not name.endswith(".md"):
            continue
        m = _CASE_FILENAME_RE.match(name)
        if not m:
            # 兜底：当作匿名案例
            case_id = os.path.splitext(name)[0]
        else:
            case_id = m.group(1)
        path = os.path.join(case_dir, name)
        try:
            text = _read_text(path)
        except OSError as e:
            logger.warning("读取案例失败 %s: %s", path, e)
            continue
        out.append(
            {
                "id": f"case:{case_id}",
                "tenant_id": tenant_id,
                "text": _truncate(text),
                "metadata": {
                    "kind": "case",
                    "case_id": case_id,
                    "source": path,
                },
            }
        )
    return out


# =====================================================
# 主流程
# =====================================================
async def async_main(args: argparse.Namespace) -> int:
    project_root = _PROJECT_ROOT
    reg_dir = (
        args.reg_dir
        if os.path.isabs(args.reg_dir)
        else os.path.join(project_root, args.reg_dir)
    )
    case_dir = (
        args.case_dir
        if os.path.isabs(args.case_dir)
        else os.path.join(project_root, args.case_dir)
    )
    tenant_id = args.tenant

    if not os.path.isdir(reg_dir) and not os.path.isdir(case_dir):
        print(f"reg_dir 和 case_dir 都不存在: {reg_dir} / {case_dir}", file=sys.stderr)
        return 1

    records = _scan_regulations(reg_dir, tenant_id) + _scan_cases(case_dir, tenant_id)
    if not records:
        print("未发现任何待索引文件（regulations / cases 都为空或无合法命名）")
        return 0

    if args.dry_run:
        for r in records:
            print(
                f"  [DRY] {r['id']}  kind={r['metadata'].get('kind')}  "
                f"len={len(r['text'])}"
            )
        return 0

    store, VectorRecord = _make_store()
    if args.stats:
        print(
            f"向量库统计: total={store.count()} tenant={tenant_id}={store.count(tenant_id)}"
        )
        return 0

    # upsert
    rec_objs = [VectorRecord(**r) for r in records]
    n = await store.upsert(rec_objs)
    print(f"已 upsert {n} 条记录（tenant={tenant_id}）")
    print(
        f"  法规: {sum(1 for r in records if r['metadata'].get('kind') == 'regulation')}"
    )
    print(
        f"  案例: {sum(1 for r in records if r['metadata'].get('kind') == 'case')}"
    )
    print(f"  store.count(tenant={tenant_id}) = {store.count(tenant_id)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="阶段 4d：向量库初始化")
    parser.add_argument("--reg-dir", default="data/regulations", help="法规目录")
    parser.add_argument("--case-dir", default="data/cases", help="案例目录")
    parser.add_argument("--tenant", default="tnt_default", help="租户 ID")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不入库")
    parser.add_argument("--stats", action="store_true", help="只打印当前 store 统计")
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
