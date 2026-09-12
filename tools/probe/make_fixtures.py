"""生成探针夹具：每个角色一份最小 messages 占位文件。

夹具的作用只是「提供 messages 数组的骨架」——探针会把**末条 user** 换成场景文本。
system 内容默认留空，探针用 `--assemble` 现场按 `idiolect.assemble` 装配；
如果你有自己的真实运行时 dump（含记忆/世界状态），把它放进 `fixtures/` 覆盖同名文件，
并去掉 `--assemble`，探针就会用你那份完整 prompt。

用法：
    py -X utf8 tools/probe/make_fixtures.py            # 只补缺失的
    py -X utf8 tools/probe/make_fixtures.py --force    # 覆盖已有
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 仓库根 + tools/ 上 sys.path（_paths 在 tools/ 下）
_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from _paths import ROOT  # noqa: E402

CHARS = ["爱音", "灯", "立希", "素世", "乐奈"]
FIXTURES = ROOT / "fixtures"

PLACEHOLDER = (
    "（占位夹具：system 留空，探针用 idiolect.assemble 现场装配；"
    "这条 user 会被探针替换成场景文本）"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已存在的夹具")
    args = ap.parse_args()

    FIXTURES.mkdir(parents=True, exist_ok=True)
    made = skipped = 0
    for char in CHARS:
        dst = FIXTURES / f"messages_{char}.json"
        if dst.exists() and not args.force:
            skipped += 1
            continue
        dst.write_text(json.dumps([
            {"role": "system", "content": ""},
            {"role": "user", "content": PLACEHOLDER},
        ], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        made += 1
    print(f"夹具目录 {FIXTURES}：新写 {made} 份，跳过 {skipped} 份")
    return 0


if __name__ == "__main__":
    sys.exit(main())
