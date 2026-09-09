"""对比 shu_zhuang_tu.txt 描述的目录树与 construction-ai-agents/ 实际文件。"""
import re
from pathlib import Path

# 跨平台
ROOT = Path(__file__).resolve().parents[2] / "construction-ai-agents"
TREE_FILE = Path(__file__).resolve().parents[2] / "shu_zhuang_tu.txt"


def parse_tree(text: str):
    """解析树状文本，返回 (rel_path, is_dir) 列表，路径相对 ROOT。"""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    result = []
    stack: list[str] = []
    item_pattern = re.compile(r'[├└]──\s+(.+)')

    for line in lines:
        match = item_pattern.search(line)
        if not match:
            continue
        start = match.start()
        level = start // 4 + 1
        target_len = level - 1
        while len(stack) > target_len:
            stack.pop()
        if target_len > len(stack):
            stack.extend([''] * (target_len - len(stack)))
        item_str = match.group(1).strip()
        if ' #' in item_str:
            item_str = item_str.split(' #')[0].strip()
        item_str = item_str.rstrip()
        is_dir = item_str.endswith('/')
        name = item_str.rstrip('/')
        parent_rel = '/'.join(stack)
        rel_path = f"{parent_rel}/{name}" if parent_rel else name
        result.append((rel_path, is_dir))
        if is_dir:
            stack.append(name)
    return result


tree_text = TREE_FILE.read_text(encoding='utf-8')
root = ROOT

items = parse_tree(tree_text)
expected_files, expected_dirs = set(), set()
for rel_path, is_dir in items:
    (expected_dirs if is_dir else expected_files).add(rel_path)

actual_files, actual_dirs = set(), set()
for p in root.rglob('*'):
    rel = p.relative_to(root).as_posix()
    (actual_dirs if p.is_dir() else actual_files).add(rel)

print(f'期望: 目录 {len(expected_dirs)} / 文件 {len(expected_files)}')
print(f'实际: 目录 {len(actual_dirs)} / 文件 {len(actual_files)}')
print()
print('=== 缺少的文件 ===')
[print(' ', f) for f in sorted(expected_files - actual_files)] or print('  (无)')
print('=== 缺少的目录 ===')
[print(' ', d) for d in sorted(expected_dirs - actual_dirs)] or print('  (无)')
print('=== 多余的文件 ===')
[print(' ', f) for f in sorted(actual_files - expected_files)] or print('  (无)')
print('=== 多余的目录 ===')
[print(' ', d) for d in sorted(actual_dirs - expected_dirs)] or print('  (无)')

# 空文件统计
non_empty = [f for f in sorted(actual_files) if (root / f).stat().st_size > 0]
empty = [f for f in sorted(actual_files) if (root / f).stat().st_size == 0]
print(f'\n非空文件数: {len(non_empty)} / 空文件数: {len(empty)}')
print('\n--- 非空文件清单 ---')
for f in non_empty:
    print(f'  {(root / f).stat().st_size:>6} B  {f}')

