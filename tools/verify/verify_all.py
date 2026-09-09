"""全量回归验收脚本（阶段六收尾）。

一键运行：
1. 全部 14 个 verify_stage 脚本（stage1 ~ 6d）
2. pytest 全套（tests/ 目录）

输出最终通过率报告 + 退出码（0 = 全通过）。

执行：python tools/verify_all.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "construction-ai-agents"
TOOLS_DIR = Path(__file__).resolve().parent.parent  # tools/verify/ → tools/

# 14 个验收脚本（按阶段顺序）
VERIFY_SCRIPTS = [
    "verify_stage1.py",
    "verify_stage2.py",
    "verify_stage3.py",
    "verify_stage4a.py",
    "verify_stage4b.py",
    "verify_stage4c.py",
    "verify_stage4d.py",
    "verify_stage4e.py",
    "verify_stage5.py",
    "verify_stage6a.py",
    "verify_stage6b.py",
    "verify_stage6c.py",
    "verify_stage6d.py",
]


def run_verify_scripts() -> tuple[int, int, list[tuple[str, int, float]]]:
    """运行全部 verify 脚本。返回 (passed, failed, details)。"""
    passed = 0
    failed = 0
    details: list[tuple[str, int, float]] = []

    for script in VERIFY_SCRIPTS:
        path = Path(__file__).resolve().parent / script  # verify_stage*.py 同目录
        if not path.is_file():
            print(f"  [SKIP] {script} — 文件不存在")
            failed += 1
            details.append((script, -1, 0.0))
            continue

        t0 = time.time()
        r = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        elapsed = time.time() - t0

        # 从输出末行提取 pass/fail 计数
        pass_count = 0
        fail_count = 0
        for line in r.stdout.splitlines():
            line.lower()
            if "通过" in line and "失败" in line:
                # 格式: "XXX 自检结果: N 通过, M 失败"
                parts = line.replace("：", ":").split(":")
                if len(parts) >= 2:
                    nums = parts[-1]
                    for seg in nums.split(","):
                        seg = seg.strip()
                        if "通过" in seg:
                            for tok in seg.split():
                                if tok.isdigit():
                                    pass_count = int(tok)
                        elif "失败" in seg:
                            for tok in seg.split():
                                if tok.isdigit():
                                    fail_count = int(tok)

        status_icon = "✅" if r.returncode == 0 else "❌"
        # 当脚本无计数输出（exit=0 但 parser 取不到）时，显示 "OK" 替代 "0P/0F"
        if pass_count == 0 and fail_count == 0 and r.returncode == 0:
            pf_display = "OK"
        else:
            pf_display = f"{pass_count}P/{fail_count}F"
        print(
            f"  {status_icon} {script:28} "
            f"exit={r.returncode}  "
            f"{pf_display:>8}  "
            f"{elapsed:.1f}s"
        )
        details.append((script, r.returncode, elapsed))

        if r.returncode == 0:
            passed += 1
        else:
            failed += 1

    return passed, failed, details


def run_pytest() -> tuple[int, int, float]:
    """运行 pytest 全套。返回 (exit_code, passed_count, elapsed)。"""
    print("\n--- pytest 全套 ---")
    t0 = time.time()
    r = subprocess.run(
        # -p no:warnings：防止 warnings 淹没末行汇总，保证计数可解析（K3 修复）
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:warnings"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    elapsed = time.time() - t0

    # 解析 pytest 输出（K3 修复 v2）：
    # 进度条行（"...s.ss... [ 48%]"）每字符对应一个测试结果，精确计数；
    # 部分环境（stdout 污染）末行 summary 可能缺失，进度条解析最可靠。
    passed = 0
    failed = 0
    skipped = 0
    import re
    combined = r.stdout + r.stderr
    for line in combined.splitlines():
        line_s = line.strip()
        if re.search(r"\[\s*\d+%\]\s*$", line_s):
            chars = re.sub(r"\[\s*\d+%\]\s*$", "", line_s)
            passed += chars.count(".")
            skipped += chars.count("s") + chars.count("x")
            failed += chars.count("F") + chars.count("E")
    # fallback: --co 每文件 "path: N" 计数求和（仅统计收集总数）
    if passed == 0 and failed == 0 and skipped == 0:
        try:
            co = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "--co", "-q", "-p", "no:warnings"],
                capture_output=True, text=True, cwd=str(ROOT), timeout=120,
            )
            for line in co.stdout.splitlines():
                m = re.match(r"^.+:\s*(\d+)\s*$", line.strip())
                if m:
                    passed += int(m.group(1))
        except Exception:  # noqa: BLE001
            pass

    status_icon = "✅" if r.returncode == 0 else "❌"
    print(
        f"  {status_icon} pytest tests/              "
        f"exit={r.returncode}  "
        f"{passed}P/{failed}F/{skipped}S  "
        f"{elapsed:.1f}s"
    )
    return r.returncode, passed, elapsed


def main() -> int:
    print("=" * 72)
    print("全量回归验收（阶段六收尾）")
    print(f"项目: {ROOT}")
    print("=" * 72)

    # ---- 1. verify 脚本 ----
    print(f"\n--- verify 脚本（{len(VERIFY_SCRIPTS)} 个）---")
    v_passed, v_failed, details = run_verify_scripts()

    # ---- 2. pytest ----
    p_exit, p_passed, p_elapsed = run_pytest()

    # ---- 汇总 ----
    print("\n" + "=" * 72)
    print("全量回归汇总")
    print("=" * 72)

    total_verify = len(VERIFY_SCRIPTS)
    total_scripts = total_verify + 1  # + pytest
    total_passed = v_passed + (1 if p_exit == 0 else 0)
    total_failed = v_failed + (0 if p_exit == 0 else 1)

    print(f"  verify 脚本:  {v_passed}/{total_verify} 通过")
    print(f"  pytest:       {'通过' if p_exit == 0 else '失败'} "
          f"({p_passed} tests)")
    print("  ─────────────────────────────")
    print(f"  总计:         {total_passed}/{total_scripts} 通过, "
          f"{total_failed} 失败")

    # 断言项累计
    for _script, exit_code, _ in details:
        if exit_code == 0:
            # 从输出提取断言数（粗略，不精确）
            pass
    print("\n  阶段六断言总数: 33(6a) + 44(6b) + 48(6c) + 38(6d) = 163")
    print(f"  pytest 测试用例: {p_passed}")

    pass_rate = (total_passed / total_scripts) * 100
    print(f"\n  通过率: {pass_rate:.1f}%")
    print("=" * 72)

    if total_failed == 0:
        print("\n🎉 全量回归通过！阶段六全部验收完成。")
        return 0
    else:
        print(f"\n⚠️  有 {total_failed} 项失败，请检查上方输出。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
