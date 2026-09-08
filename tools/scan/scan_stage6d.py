"""阶段六·子阶段 6d（Dockerfile.edge + BIM 连接器 API）目标文件清单。

覆盖：
- 6d.1 Dockerfile.edge + BIM 数据 API + 连接器降级（Task 11）

执行：python scan_stage6d.py
退出码：0 = 全部就位且非空；非 0 = 有缺失/空壳。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"

# 6d 新增文件（必须存在且非空）
STAGE6D_NEW = [
    # 6d.1 BIM 数据 API + 边缘端容器（Task 11）
    "api/schemas/bim_schemas.py",
    "api/routers/bim_router.py",
    "deployment/docker/Dockerfile.edge",
    "tests/integration/test_bim_edge.py",
]

# 6d 改造文件（必须存在且非空；内容由 verify_stage6d 运行期校验）
STAGE6D_MODIFIED = [
    "api/routers/__init__.py",
    "api/schemas/__init__.py",
    "api/main.py",
]


def main() -> int:
    print(f"{'path':68} {'size':>8}  status")
    print("-" * 88)
    missing = 0
    empty = 0
    ok = 0
    for rel in STAGE6D_NEW + STAGE6D_MODIFIED:
        p = ROOT / rel
        if not p.is_file():
            print(f"{rel:68} {'-':>8}  MISSING")
            missing += 1
            continue
        size = p.stat().st_size
        if size == 0:
            print(f"{rel:68} {size:>8}  EMPTY")
            empty += 1
        else:
            tag = "OK " if rel in STAGE6D_NEW else "OK*"
            print(f"{rel:68} {size:>8}  {tag}")
            ok += 1
    total = len(STAGE6D_NEW) + len(STAGE6D_MODIFIED)
    print("-" * 88)
    print(f"已实现: {ok}   0 字节占位: {empty}   不存在: {missing}   合计: {total}")
    print("(OK  = 6d 新增文件；OK* = 6d 改造文件，运行期行为由 verify_stage6d.py 校验)")
    return 0 if missing == 0 and empty == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
