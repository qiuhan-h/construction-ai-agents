"""阶段六·子阶段 6c（移动端 API + 内嵌应用 + 响应式 Streamlit 页面）目标文件清单。

覆盖：
- 6c.1 移动端精简 API + 钉钉/企微内嵌应用（Task 8）
- 6c.2 响应式 Streamlit 移动端页面（Task 9）

执行：python scan_stage6c.py
退出码：0 = 全部就位且非空；非 0 = 有缺失/空壳。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"

# 6c 新增文件（必须存在且非空）
STAGE6C_NEW = [
    # 6c.1 移动端 API + 内嵌应用（Task 8）
    "api/routers/mobile_router.py",
    "api/schemas/mobile_schemas.py",
    "services/embedded_apps/__init__.py",
    "services/embedded_apps/dingtalk_app.py",
    "services/embedded_apps/wecom_app.py",
    "tests/integration/test_mobile_embedded.py",
    # 6c.2 响应式 Streamlit 移动端页面（Task 9）
    "streamlit_app/assets/css/mobile.css",
    "streamlit_app/components/mobile_card.py",
    "streamlit_app/pages/07_mobile.py",
    "tests/integration/test_mobile_pages.py",
]

# 6c 改造文件（必须存在且非空；内容由 verify_stage6c 运行期校验）
STAGE6C_MODIFIED = [
    # Task 8 改造
    "api/routers/__init__.py",
    "api/schemas/__init__.py",
    "api/main.py",
    # Task 9 改造
    "streamlit_app/utils/api_client.py",
    "streamlit_app/pages/__init__.py",
    "streamlit_app/app.py",
    "streamlit_app/components/__init__.py",
]


def main() -> int:
    print(f"{'path':78} {'size':>8}  status")
    print("-" * 96)
    missing = 0
    empty = 0
    ok = 0
    for rel in STAGE6C_NEW + STAGE6C_MODIFIED:
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
            tag = "OK " if rel in STAGE6C_NEW else "OK*"
            print(f"{rel:78} {size:>8}  {tag}")
            ok += 1
    total = len(STAGE6C_NEW) + len(STAGE6C_MODIFIED)
    print("-" * 96)
    print(f"已实现: {ok}   0 字节占位: {empty}   不存在: {missing}   合计: {total}")
    print("(OK  = 6c 新增文件；OK* = 6c 改造文件，运行期行为由 verify_stage6c.py 校验)")
    return 0 if missing == 0 and empty == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
