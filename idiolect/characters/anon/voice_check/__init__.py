"""anon.voice_check — 爱音回复后处理强制清洗。

设计意图（同 tomori.voice_check）：
  prompt 层规则 LLM 不一定遵守、需要 deterministic 后处理把所有偏差
  清洗到爱音 canonical form。

5 个 stage（按调用顺序）：
  Stage 0: interjection_break - 句中「语气词 + 并列连词」拆段（**永远跑**）
  Stage 1: ellipsis           - 所有省略号变体 → `······`（**永远跑、不被 gate**）
  Stage 2: tilde_qe           - 原句**只有 1 个** ?/! 时、非句首位置的它前面加 ~
  Stage 3: end_decor          - 末尾追加 ♪/~/—（♪ 概率最高、去重已有标点）
  Stage 4: phrase_tail        - 句中逗号「，」/「、」按概率替换为 ~ 或 —

mood gate（Stage 2-4）：
  effective_p = max(voice_mood, empathy) / 100
  每个 stage 独立掷骰：random() < effective_p × stage_base_factor
  · stage_base_factor 是 stage 在最高 mood 时的概率上限
  · mood 高时各 stage 都易启用、mood 低时大部分 skip 让 LLM 原 raw 透出

API:
  clean_reply(text, *, voice_mood=None, empathy=None, rng=None) -> (text, info)
"""
from __future__ import annotations

import random as _random_default
import re

from .ellipsis import (
    ANON_ELLIPSIS,
    normalize_ellipsis,
)
from .interjection_break import break_interjection_run_on

__all__ = (
    "ANON_ELLIPSIS",
    "normalize_ellipsis",
    "break_interjection_run_on",
    "clean_reply",
    # Individual stage helpers (exposed for unit tests)
    "apply_tilde_qe",
    "apply_end_decoration",
    "apply_phrase_tail",
)


# ── Stage base factors（mood=100 时的最大概率上限）─────────────
_STAGE_BASE_TILDE_QE  = 0.85   # 单 ! / ? → ~? / ~!（非句首、原句仅 1 个 ?/!）
_STAGE_BASE_END_DECOR = 0.85   # 末尾装饰 ♪/~/—
_STAGE_BASE_PHRASE    = 0.50   # 短语后 / 逗号替换

# Stage 3 内部：选哪个末尾装饰（用户拍板 2026-05-10：—→——）
_END_DECOR_SYMBOLS_WEIGHTED = (
    ("♪", 0.50),  # 最常用
    ("~", 0.30),
    ("——", 0.20),  # 双破折号、不再用单 —
)

# Stage 4 内部：每个逗号被替换的概率（stage gate 通过后）
_PHRASE_REPLACE_PROB = 0.40

# 2026-05-12 装饰密度上限：避免「——！...♪...~」一句话 4 种装饰满天飞。
# 段 = 连续的 ♪ / ~ / ～ / 2+ —— 视为 1 段。
# 单行 / 整 text 已有 >= cap 段装饰时、Stage 3/4 不再追加更多。
_DECOR_DENSITY_CAP = 2
_DECOR_SEG_RE = re.compile(r"[♪~～]|—{2,}")


def _count_decor_segments(text: str) -> int:
    """数装饰段数：♪ / ~ / ～ 每个 1 段、连续 ——（2+）算 1 段。"""
    return len(_DECOR_SEG_RE.findall(text or ""))
# 替换时选 ~ 还是 —
_PHRASE_TILDE_PROB = 0.70  # 70% 选 ~、30% 选 —

# ─────────────────────────────────────────────────────────────
# Stage 2: tilde_qe —— 非句首 ?/! 前加 ~（仅原句 1 个 ?/! 时）
# ─────────────────────────────────────────────────────────────
def apply_tilde_qe(text: str) -> tuple[str, int]:
    """在非句首位置的 ?/! 前补 ~（仅当原句**总共只有一个 ? 或一个 !** 时生效、去重）。

    用户拍板 2026-05-10：多 ?/! 不洗、保留 LLM 原节奏（避免「行吗~？真的吗~？」过密）。
    单 ?/! 才视为可能的 canon 「真的吗~？」式装饰、有概率加 ~。

    句首定义：行首（含前导空白和换行）、紧跟 ? / ! 的位置。
    多 bubble（含 \\n）每行各自判定 ?/! 总数。

    **2026-05-12 装饰密度 cap**：该行已有 ≥ _DECOR_DENSITY_CAP 段装饰时、不再加 ~
    （避免「——~！...♪」一行 4 种装饰满天飞）。
    """
    if not text:
        return text, 0
    out: list[str] = []
    fixed = 0

    # 按行处理、各行独立判定 ?/! 总数
    lines = text.split("\n")
    new_lines: list[str] = []
    for line in lines:
        # 装饰密度 cap：该行已有 >= cap 段装饰、不再加 ~
        if _count_decor_segments(line) >= _DECOR_DENSITY_CAP:
            new_lines.append(line)
            continue
        # 数本行 ?/! 总数
        q_count = sum(1 for c in line if c in "?？")
        x_count = sum(1 for c in line if c in "!！")
        # 仅在 (q_count + x_count == 1) 时才考虑加 ~
        if q_count + x_count != 1:
            new_lines.append(line)
            continue
        # 找那唯一的 ?/! 位置、判句首 + 去重
        line_out: list[str] = []
        for i, c in enumerate(line):
            if c in "?？!！":
                j = i - 1
                while j >= 0 and line[j] in " \t":
                    j -= 1
                is_head = j < 0
                already_tilde = j >= 0 and line[j] in "~～"
                if not is_head and not already_tilde:
                    line_out.append("~")
                    fixed += 1
            line_out.append(c)
        new_lines.append("".join(line_out))
    return "\n".join(new_lines), fixed


# ─────────────────────────────────────────────────────────────
# Stage 3: end_decoration —— 末尾追加 ♪/~/—
# ─────────────────────────────────────────────────────────────
_END_NEEDS_NO_DECOR = "♪~～—?？!！·…"  # 末尾若是这些字符则不加（已有装饰 / 问号感叹号 / 省略号）
# (· 含中点省略号、… 含 horizontal ellipsis)
# 注：句号「。」/「.」**不在此列**——canon 上 ♪/~/— 等同于句号、需要**替换**而非追加。


def _pick_end_symbol(rng) -> str:
    """按权重选 ♪/~/—。"""
    r = rng.random()
    cum = 0.0
    for sym, w in _END_DECOR_SYMBOLS_WEIGHTED:
        cum += w
        if r < cum:
            return sym
    return _END_DECOR_SYMBOLS_WEIGHTED[-1][0]


def apply_end_decoration(text: str, rng) -> tuple[str, int]:
    """末尾追加 ♪/~/— 之一。多行各行末独立处理。

    canon 关键：♪/~/— 在爱音句末等同于句号——
      · 末尾是「。」/「.」时、**先剥掉句号**再加装饰（不是「。♪」、是「♪」）
      · 末尾已是 ?/! / ♪/~/— / ······ / … 时跳过（不重复加 / 不替换）
      · **2026-05-12 装饰密度 cap**：该行已有 ≥ _DECOR_DENSITY_CAP 段装饰时跳过
        （避免「——！...♪~」一行 4 种装饰满天飞）
    """
    if not text:
        return text, 0
    fixed = 0
    out_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.rstrip()
        if not stripped:
            out_lines.append(line)
            continue
        # 装饰密度 cap：该行已有 >= cap 段装饰、不再加末尾
        if _count_decor_segments(line) >= _DECOR_DENSITY_CAP:
            out_lines.append(line)
            continue
        last = stripped[-1]
        # 已是装饰 / ?/! / 省略号 → skip
        if last in _END_NEEDS_NO_DECOR:
            out_lines.append(line)
            continue
        # 末尾是句号「。」/「.」→ 剥掉再加（装饰等同于句号）
        if last in "。.":
            stripped = stripped[:-1]
        if not stripped:  # 剥完成空（防御）
            out_lines.append(line)
            continue
        sym = _pick_end_symbol(rng)
        out_lines.append(stripped + sym)
        fixed += 1
    return "\n".join(out_lines), fixed


# ─────────────────────────────────────────────────────────────
# Stage 4: phrase_tail —— 中文逗号「，」/「、」替换为 ~ 或 —
# ─────────────────────────────────────────────────────────────
def apply_phrase_tail(text: str, rng) -> tuple[str, int]:
    """每个「，」/「、」按 _PHRASE_REPLACE_PROB 概率替换为 ~ 或 ——。

    被替换的逗号 → 70% ~ / 30% ——（双破折号、用户拍板 2026-05-10）。

    **2026-05-12 装饰密度 cap**：per-line 已有 ≥ _DECOR_DENSITY_CAP 段装饰时、
    跳过该行内的逗号替换（避免一行 4 种装饰满天飞）。
    """
    if not text:
        return text, 0
    fixed = 0
    out_lines: list[str] = []
    for line in text.split("\n"):
        # 装饰密度 cap：该行已有 >= cap 段装饰、不替换该行的 ，/、
        if _count_decor_segments(line) >= _DECOR_DENSITY_CAP:
            out_lines.append(line)
            continue
        buf: list[str] = []
        for c in line:
            if c in "，、":
                if rng.random() < _PHRASE_REPLACE_PROB:
                    replacement = "~" if rng.random() < _PHRASE_TILDE_PROB else "——"
                    buf.append(replacement)
                    fixed += 1
                    continue
            buf.append(c)
        out_lines.append("".join(buf))
    return "\n".join(out_lines), fixed


# ─────────────────────────────────────────────────────────────
# Main: clean_reply
# ─────────────────────────────────────────────────────────────
def clean_reply(
    text: str,
    *,
    voice_mood: float | None = None,
    empathy: float | None = None,
    rng=None,
) -> tuple[str, dict]:
    """爱音回复后处理总入口。

    Args:
        text: LLM 产出的回复
        voice_mood: 0-100、None 默认 70
        empathy: 0-100、None 默认 50
        rng: random.Random 注入（self-test 用、生产传 None 用默认）

    Returns:
        (cleaned_text, info_dict)
        info_dict = {
            "violations": {stage: count, ...},   # 各 stage 实际生效次数
            "ok": bool,
            "voice_mood": float | None,
            "empathy": float | None,
            "effective_p": float,                # max(vm, em) / 100
            "skipped": list[str],                # 因 gate 被 skip 的 stage
            "stage_p": {stage: float, ...},      # debug：每 stage 实际启用概率
        }

    流程：
      Stage 1 ellipsis       永远跑
      Stage 2 tilde_qe       p = effective_p × 0.85（仅原句 1 个 ?/!）
      Stage 3 end_decoration p = effective_p × 0.85
      Stage 4 phrase_tail    p = effective_p × 0.50
    """
    rng = rng or _random_default
    vm = voice_mood if voice_mood is not None else 70.0
    em = empathy if empathy is not None else 50.0
    effective_p = max(0.0, min(1.0, max(vm, em) / 100.0))

    info: dict = {
        "violations": {},
        "ok": True,
        "voice_mood": voice_mood,
        "empathy": empathy,
        "effective_p": effective_p,
        "skipped": [],
        "stage_p": {},
    }

    if not text:
        return text, info

    # Stage 0: interjection_break（永远跑、不被 gate）
    # 「[标点][语气词][并列连词]」结构 → 「[标点]\n[并列连词]」、删衔接语气词 + 换行让后端拆 bubble
    text, n0 = break_interjection_run_on(text)
    if n0:
        info["violations"]["interjection_break"] = n0
        info["ok"] = False

    # Stage 1: ellipsis（永远跑、不被 gate）
    text, n1 = normalize_ellipsis(text)
    if n1:
        info["violations"]["ellipsis"] = n1
        info["ok"] = False

    # Stage 2-4: 各自独立 gate
    stages = [
        ("tilde_qe",     _STAGE_BASE_TILDE_QE,  lambda t: apply_tilde_qe(t)),
        ("end_decor",    _STAGE_BASE_END_DECOR, lambda t: apply_end_decoration(t, rng)),
        ("phrase_tail",  _STAGE_BASE_PHRASE,    lambda t: apply_phrase_tail(t, rng)),
    ]
    for stage_name, base_factor, fn in stages:
        p = max(0.0, min(1.0, effective_p * base_factor))
        info["stage_p"][stage_name] = round(p, 3)
        if rng.random() < p:
            try:
                text, n = fn(text)
                if n:
                    info["violations"][stage_name] = n
                    info["ok"] = False
            except Exception as _err:
                info["skipped"].append(f"{stage_name}_err:{_err}")
        else:
            info["skipped"].append(stage_name)

    return text, info


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    fail = 0

    # ─── Stage 2: tilde_qe ───────────────────
    print("=== Stage 2: tilde_qe ===")
    cases_s2 = [
        ("真的吗？", "真的吗~？", 1),                  # 单 ? → ~?
        ("我去！", "我去~！", 1),                       # 单 !
        ("？小乐奈在干嘛", "？小乐奈在干嘛", 0),         # 单 ? 但句首
        ("！突然", "！突然", 0),                        # 单 ! 但句首
        ("好啊~？", "好啊~？", 0),                     # 已有 ~ 不重复
        ("行吗？真的吗？", "行吗？真的吗？", 0),         # 双 ?、不洗（新规则）
        ("我去！哇！", "我去！哇！", 0),                 # 双 !、不洗
        ("好啊？！", "好啊？！", 0),                    # 一 ? 一 ! = 双总数、不洗
        ("", "", 0),
        ("没有问号的句子", "没有问号的句子", 0),
        ("第一行?\n?第二行", "第一行~?\n?第二行", 1),    # 多行各行独立、第一行单 ? 加~、第二行单 ? 但句首
    ]
    for inp, exp, exp_n in cases_s2:
        out, n = apply_tilde_qe(inp)
        ok = (out == exp) and (n == exp_n)
        if not ok: fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {inp!r:30} -> {out!r:30} n={n} (exp {exp!r}, exp_n={exp_n})")

    # ─── Stage 3: end_decoration ───────────────────
    print()
    print("=== Stage 3: end_decoration ===")
    rng_d = _random_default.Random(42)
    cases_s3 = [
        ("好啊", True),                 # 应该加
        ("真的吗？", False),            # 末尾 ? 不加
        ("好啊♪", False),               # 已有 ♪ 不加
        ("好啊~", False),
        ("好啊—", False),
        ("好啊······", False),          # 末尾 ······ 不加
        ("好啊…", False),
        ("好啊。", False),
        ("", False),
        ("第一行\n第二行", True),        # 多行各自处理（这里会加在第二行末尾、第一行也加）
    ]
    for inp, should_change in cases_s3:
        out, n = apply_end_decoration(inp, rng_d)
        ok = (n > 0) == should_change
        # 多行 case 特别检验：第一行也会被装饰
        if not ok: fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {inp!r:30} -> {out!r:35} n={n} (should_change={should_change})")

    # ─── Stage 4: phrase_tail ───────────────────
    print()
    print("=== Stage 4: phrase_tail ===")
    rng_p = _random_default.Random(42)
    # 多次跑、统计是否有替换发生（不能精确断 case、概率性）
    inp = "真好啊，可以用这样的吉他，太开心了"
    n_reps = 100
    total_replaced = 0
    for _ in range(n_reps):
        rng_x = _random_default.Random(_)
        out, n = apply_phrase_tail(inp, rng_x)
        total_replaced += n
    avg = total_replaced / n_reps
    # 输入有 2 个「，」、_PHRASE_REPLACE_PROB=0.40 → 期望约 0.8 / case
    expect_lo, expect_hi = 0.5, 1.2
    ok = expect_lo <= avg <= expect_hi
    if not ok: fail += 1
    print(f"[{'PASS' if ok else 'FAIL'}] avg replaced over 100 runs = {avg:.2f} (expect {expect_lo}-{expect_hi})")

    # ─── 端到端 clean_reply：mood 三档分布测试 ───────────────────
    print()
    print("=== clean_reply: mood gate distribution ===")
    sample = "真的吗，怎么会这样"
    n_runs = 200
    for vm_lvl, label in [(95.0, "高 mood"), (70.0, "中 mood"), (30.0, "低 mood")]:
        skipped_counts: dict = {}
        for k in range(n_runs):
            rng_x = _random_default.Random(k * 31)
            _, info = clean_reply(sample, voice_mood=vm_lvl, empathy=50.0, rng=rng_x)
            for sk in info["skipped"]:
                skipped_counts[sk] = skipped_counts.get(sk, 0) + 1
        rate = {k: f"{v/n_runs:.2%}" for k, v in skipped_counts.items()}
        print(f"  {label} (vm={vm_lvl}): skipped rates = {rate}")

    # ─── 一致性快速 case ───────────────────
    print()
    print("=== sanity: stage chain on real reply ===")
    examples = [
        ("呐呐，我们要不要去原宿呢", 95.0, 50.0),
        ("嗯", 30.0, 50.0),
        ("怎么会这样啊", 80.0, 50.0),
        ("好啊，去看吧", 70.0, 50.0),
    ]
    for text, vm, em in examples:
        rng_e = _random_default.Random(7)
        out, info = clean_reply(text, voice_mood=vm, empathy=em, rng=rng_e)
        v = info["violations"]
        sk = info["skipped"]
        print(f"  vm={vm}: {text!r:30} -> {out!r:40} v={v} skipped={sk}")

    print()
    print(f"OVERALL: {'PASS' if fail == 0 else f'FAIL ({fail})'}")
