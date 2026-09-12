"""探针跑完的**标准收尾**：一条命令 = 打分 + 并排对照 + 复读/复述审计 + 池化比较。

用户 2026-09-12 的要求：「测试完 LLM 表现后要记得打分和与原作场景比较」。
实测又补了三件必须一起看的：**同格重复度**（长度看不出「6 条里 5 条一样」）、
**示例复述审计**（直接量回复有没有照抄注入正文）、
**池化比较**（单臂 n=6 的摆动大于效应，结论只认池化）。
零散的脚本容易漏跑，所以这里合成一条入口。方法学见
`docs/brain/character/prompt_distillation_evaluation.md`。

用法：
    # 最小：打分 + 单场景并排
    py -X utf8 probe_report.py --label gen_on10 --scene crisis

    # 完整四件套（通用场景臂）
    py -X utf8 probe_report.py --label gen_on10 --scenes crisis,comfort,low_mood \\
        --cat 通用场景 --off-labels gen_off2 --on-labels gen_on8,gen_on9,gen_on10

    # 与另一臂逐场景对比
    py -X utf8 probe_report.py --label gen_on10 --with-ab gen_off2

步骤（都是独立脚本，可单独重跑）：
  1. `scene_distill.py`     分布级评分（中位/p90/句数 vs 原作同场景基线 + excess）
  2. `scene_feedback.py`    模型回复 vs 原作同场景台词并排（每个 --scenes 一项）
  3. `_repeat_rate.py`      同格重复度（distinct/6）—— 专治复读
  4. `_copy_audit.py`       逐字复述审计（回复是否含注入块的引用 + 最长公共子串）
  5. `_pool_arms.py`        多臂池化后的蒸馏均值 + 逐格改善数
  6. `scene_ab_compare.py`  可选，与另一臂逐场景对比

产物都落在 `report/` 下（文件名含 label，便于回溯）。
"""
from __future__ import annotations

# ── idiolect 路径引导（可移植）：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _run(script: str, *args: str) -> int:
    cmd = [sys.executable, str(HERE / script), *args]
    print(f"\n{'=' * 72}\n$ {script} {' '.join(args)}\n{'=' * 72}", flush=True)
    # 子进程显式 UTF-8：父进程捕获 stdout 时默认会用本地代码页，
    # 中文会变成乱码（还会让管道调用方看到伪非零退出码）。
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.call(cmd, cwd=str(HERE), env=env)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="probe 轮次名（report/probe_<label>.jsonl）")
    ap.add_argument("--scene", default="", help="[旧参数] 单个并排对照的场景 key")
    ap.add_argument("--scenes", default="", help="并排对照的场景 key（逗号分隔，逐个跑）")
    ap.add_argument("--extra-labels", default="", help="额外一起打分的轮次（逗号分隔）")
    ap.add_argument("--labels-for-feedback", default="", help="并排对照要用的轮次（缺省只用 --label）")
    ap.add_argument("--cat", default="", help="复述审计的夹具类别（深模块 / 通用场景）")
    ap.add_argument("--copy-labels", default="", help="复述审计要比较的臂（缺省 = --label）")
    ap.add_argument("--repeat-intra", action="store_true",
                    help="同格重复度只算 --label（默认：若给了 --extra-labels 则一起算）")
    ap.add_argument("--off-labels", default="", help="池化比较的基线臂（逗号分隔）")
    ap.add_argument("--on-labels", default="", help="池化比较的注入臂（逗号分隔）")
    ap.add_argument("--pool-scenes", default="", help="池化比较只算这些场景（逗号分隔，可选）")
    ap.add_argument("--with-ab", default="", help="与这一臂做逐场景对比（scene_ab_compare）")
    args = ap.parse_args()

    jsonl = REPORT / f"probe_{args.label}.jsonl"
    if not jsonl.exists():
        print(f"[probe_report] 找不到 {jsonl} —— 先跑 probe_runner", file=sys.stderr)
        return 2

    rc = 0
    labels = ",".join(x for x in (args.label, args.extra_labels) if x)

    # ① 分布级评分
    rc |= _run("scene_distill.py", "--labels", labels)

    # ② 并排对照（每个场景一项）
    scenes = [s for s in (args.scenes or args.scene).split(",") if s]
    fb_labels = args.labels_for_feedback or args.label
    for sc in scenes:
        rc |= _run("scene_feedback.py", "--scene", sc, "--labels", fb_labels, "--n", "6")

    # ③ 同格重复度
    if args.repeat_intra:
        rc |= _run("_repeat_rate.py", args.label)
    else:
        rc |= _run("_repeat_rate.py", labels)

    # ④ 示例复述审计
    if args.cat:
        rc |= _run("_copy_audit.py", "--cat", args.cat,
                   "--labels", args.copy_labels or args.label, "--detail")

    # ⑤ 池化比较
    if args.off_labels and args.on_labels:
        pool_args = [args.off_labels, args.on_labels]
        if args.pool_scenes:
            pool_args.append(args.pool_scenes)
        rc |= _run("_pool_arms.py", *pool_args)

    # ⑥ 可选：逐场景对比
    if args.with_ab:
        rc |= _run("scene_ab_compare.py", "--before", args.with_ab, "--after", args.label)

    print(f"\n[probe_report] 完成。产物：report/scene_distill.md、report/scene_feedback_<scene>.md"
          f"{'、report/scene_distill_<label>.json' if True else ''}")
    return 1 if rc else 0


if __name__ == "__main__":
    raise SystemExit(main())
