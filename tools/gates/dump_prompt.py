"""全量 prompt dump：回答「这个角色这一刻发给模型的 prompt 到底长什么样」。

对应原项目的 `scripts/dump_live_chat_prompt.py`（那条路径经 offline_smoke →
chat_server 装配真实运行时 prompt）。本仓库没有 session / 记忆 / 世界状态，
能 dump 的就是「角色怎么说话」这条线：canon + 语气 manifest + 场景化长度目标
+ turn_logic。方法论上这四层是**唯一**被蒸馏特征直接改写的部分，所以 dump 它们
就足以回答「特征有没有真的进 prompt」。

三件产物（都在 `report/`，可用 `IDIOLECT_REPORT_DIR` 改）：

  · `prompt_<char>_<label>.json` —— **最终 messages 数组**（分析首选；
    与探针喂给模型的对象逐字节相同）
  · `prompt_<char>_<label>.txt`  —— 全文审计版（分层小标题 + 逐层字符数）
  · `prompt_<char>_<label>.layers.json` —— 各层字符数（用于 prompt diff 门禁）

用法：

    # 单角色：一句话看四层
    py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --msg "你今天又想去哪找猫"

    # 五个人同一句话（对比同一场景下五套约束的差异）
    py -X utf8 tools/gates/dump_prompt.py --all --msg "明天几点上课" --label schedule

    # prompt diff 门禁：改动前后各跑一次，用同一 --label 的前后缀区分
    py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase before
    py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase after

    # 只看某一层 / 关掉某一层（排查该层是不是在撑 prompt）
    py -X utf8 tools/gates/dump_prompt.py --char 灯 --msg "我一直在哭" --layers canon,voice

`--phase before` 会把深模块与通用场景层的 env 回退开关全部置 0（改动前行为），
`after` 用当前代码：两臂同一脚本、同一输入、同一 mock 时刻，可以直接对 diff。
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
import json
import sys
from pathlib import Path

sys.path.insert(0, str(ROOT))

import mock_clock as MOCK  # noqa: E402
from dump_turn_logic_gate import CASES as GATE_CASES  # noqa: E402

CHARS = ["爱音", "灯", "立希", "素世", "乐奈"]
CHARKEY = {"爱音": "anon", "灯": "tomori", "立希": "taki", "素世": "soyo", "乐奈": "rana"}
LAYERS = ("canon", "voice", "style_target", "turn_logic")

# 默认矩阵：每个角色取几条**会命中不同层**的话，覆盖最常被改动的路径
DEFAULT_MATRIX = [
    ("plain", "在干嘛"),
    ("schedule", "明天几点上课"),
    ("comfort", "我一直在哭，快撑不住了"),
    ("banter", "今天天气不错，午饭吃什么"),
]


def _disable_flags() -> None:
    """before 臂：把深模块与通用场景层的 env 回退开关全部置 0。"""
    from dump_turn_logic_gate import DEEP_FLAGS, GENERAL_FLAGS

    for flags in DEEP_FLAGS.values():
        for f in flags:
            import os
            os.environ[f] = "0"
    import os
    for f in GENERAL_FLAGS:
        os.environ[f] = "0"


def _enable_flags() -> None:
    import os
    from dump_turn_logic_gate import DEEP_FLAGS, GENERAL_FLAGS

    for flags in DEEP_FLAGS.values():
        for f in flags:
            os.environ.pop(f, None)
    for f in GENERAL_FLAGS:
        os.environ.pop(f, None)


def assemble(char: str, msg: str, session_id: str, want: tuple[str, ...]):
    """按指定层装配；返回 (system, layers dict)。"""
    from idiolect.registry import get_canon_profile, get_voice_manifest, render_turn_special_block
    from idiolect.scene_classifier import classify
    from idiolect.style_target import build_style_target_block

    now = MOCK.mock_now()
    scene = classify(msg, char) if msg else ""
    pieces = {
        "canon": (get_canon_profile(char) or "").strip(),
        "voice": (get_voice_manifest(char) or "").strip(),
        "style_target": build_style_target_block(char, scene),
        "turn_logic": render_turn_special_block(
            char, msg, session_id=session_id, is_developer=False, mode="chat", now_jst=now) or "",
    }
    pieces = {k: v.strip() for k, v in pieces.items()}
    kept = {k: v for k, v in pieces.items() if k in want and v}
    return "\n\n".join(kept[k] for k in LAYERS if k in kept), pieces, scene


def write_dump(char: str, label: str, msg: str, phase: str, want: tuple[str, ...],
               quiet: bool = False) -> dict:
    """落盘一份 dump，返回摘要 dict。"""
    session_id = f"dump:{phase}:{label}:{char}"
    system, pieces, scene = assemble(char, msg, session_id, want)
    hist: list[dict] = []
    fixture = ROOT / "fixtures" / f"messages_{char}.json"
    if fixture.exists():
        try:
            rows = json.loads(fixture.read_text(encoding="utf-8"))
            hist = [r for r in rows[1:] if isinstance(r, dict) and r.get("role") != "system"]
        except Exception:  # noqa: BLE001
            hist = []
    messages = [{"role": "system", "content": system}] + hist + [{"role": "user", "content": msg}]

    tag = f"{CHARKEY[char]}_{phase}_{label}"
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / f"prompt_{tag}.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT / f"prompt_{tag}.layers.json").write_text(
        json.dumps({"char": char, "phase": phase, "label": label, "msg": msg, "scene": scene,
                    "layer_chars": {k: len(v) for k, v in pieces.items()},
                    "total_chars": len(system)}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# prompt dump · {char} · phase={phase} · label={label}",
        f"- 时钟：{MOCK.describe()}",
        f"- 命中场景：{scene or '(未命中)'}｜system 合计 {len(system)} 字符",
        f"- 本轮 user：{msg}",
        "",
    ]
    for key in LAYERS:
        body = pieces.get(key, "")
        flag = "" if key in want else "（本次未装配）"
        lines += [f"{'=' * 72}", f"## {key}{flag} · {len(body)} 字符", "=" * 72, body or "(空)", ""]
    lines += ["=" * 72, "## messages 数组（逐字节等于探针喂给模型的对象）", "=" * 72,
              json.dumps(messages, ensure_ascii=False, indent=2)]
    (REPORT / f"prompt_{tag}.txt").write_text("\n".join(lines), encoding="utf-8")

    if not quiet:
        sizes = "  ".join(f"{k}={len(pieces.get(k, ''))}" for k in LAYERS)
        print(f"[dump] {char:<4} {phase:<6} {label:<10} scene={scene or '-':<18} "
              f"system={len(system):>6}  {sizes}")
    return {"char": char, "phase": phase, "label": label, "scene": scene,
            "total_chars": len(system), "layer_chars": {k: len(pieces.get(k, "")) for k in LAYERS}}


def main() -> int:
    ap = argparse.ArgumentParser(description="全量 prompt dump（四层约束逐层可见）")
    ap.add_argument("--char", default="", help="角色名（中文或罗马字）")
    ap.add_argument("--all", action="store_true", help="五人都 dump")
    ap.add_argument("--msg", default="", help="本轮 user 文本")
    ap.add_argument("--matrix", action="store_true",
                    help=f"用内置场景矩阵（默认 {len(DEFAULT_MATRIX)} 条，会命中不同层）")
    ap.add_argument("--label", default="", help="产物后缀（禁用作对比标签）")
    ap.add_argument("--phase", choices=("before", "after"), default="after",
                    help="before = 深模块/通用场景层 env 回退开关全关（改动前行为）")
    ap.add_argument("--layers", default=",".join(LAYERS),
                    help=f"只装配这些层（逗号分隔，可选 {','.join(LAYERS)}）")
    ap.add_argument("--mock-now", default="", help="覆盖 mock 时刻（ISO 8601）")
    ap.add_argument("--case", default="", help="用 turn_logic 门禁里的场景名（如 general.comfort）")
    args = ap.parse_args()

    if args.mock_now:
        import os
        os.environ[MOCK.ENV_VAR] = args.mock_now
    if args.phase == "before":
        _disable_flags()
    else:
        _enable_flags()

    want = tuple(x for x in args.layers.split(",") if x)
    bad = [x for x in want if x not in LAYERS]
    if bad:
        print(f"未知层 {bad}；可选 {LAYERS}")
        return 2

    chars = CHARS if args.all else []
    if args.char:
        from idiolect.registry import canonicalize_name
        name = canonicalize_name(args.char)
        if not name:
            print(f"不认识的角色 {args.char!r}；可选 {CHARS}")
            return 2
        chars = [name]
    if not chars:
        print("要么给 --char，要么给 --all")
        return 2

    jobs: list[tuple[str, str]] = []  # (label, msg)
    if args.case:
        owner = args.case
        for ch, cases in GATE_CASES.items():
            for text, _want_fire, own in cases:
                if own == owner:
                    jobs.append((owner.replace(".", "_"), text))
                    break
    if args.matrix:
        jobs += DEFAULT_MATRIX
    if args.msg:
        jobs.append((args.label or "msg", args.msg))
    if not jobs:
        print("要么给 --msg，要么给 --matrix / --case")
        return 2

    print(f"[dump] 时钟 = {MOCK.describe()}")
    print(f"[dump] phase={args.phase}｜层 = {','.join(want)}｜角色 {len(chars)} × 场景 {len(jobs)}")
    print("-" * 100)
    rows = []
    for char in chars:
        for label, msg in jobs:
            rows.append(write_dump(char, label, msg, args.phase, want))
    out = REPORT / f"prompt_dump_index_{args.phase}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("-" * 100)
    print(f"-> {REPORT}\\prompt_<char>_{args.phase}_<label>.json / .txt / .layers.json")
    print(f"-> {out.name}（{len(rows)} 份，可与其他 phase 比对）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
