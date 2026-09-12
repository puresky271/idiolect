"""爱音省略号 normalize（项目级 canonical：6 中点 `······`）。

设计起点（用户拍板 2026-05-10）：
  和灯一样、爱音的 3 点省略号也自动被替换为 6 中点的特殊省略号。
  实质上 5 个角色都用 6 中点 canonical（项目级标准）、爱音此处只是把这条规则
  落地到自己的清洗管线、跟 `tomori/voice_check/ellipsis.py` 同款。

清洗目标（任何变体都归一到 `······`）：
  - `…`  (单个 U+2026 horizontal ellipsis = 视觉 3 点)
  - `……` (双 U+2026 = 视觉 6 点)、形式视觉对但字符不对
  - `………` (3+ U+2026)
  - `...` / `....` / `......` (3+ ASCII period)
  - `···` / `····` 等（中点数量不是 6）
  - `——` / `———` (双破折号；爱音的 `—` 单破折号是 canon 拖音、保留；只清"双破折号当省略号"用)

→ 全部 normalize 到 `······`（6 个 U+00B7）

设计要点（2026-05-10 用户拍板：爱音拖音 — 升级为 ——）：
  · 已经是 `······`（恰好 6 个 U+00B7）的不动、不计 violation
  · 中点数量不是 6 时（5 / 7 / 8 ...）也 normalize 到 6
  · **双 `——`（恰好 2 个全角破折号）爱音保留**——这是爱音新 canon 拖音符
  · 单 `—` 也保留（避免破坏英文输入里的 hyphen / dash）、不升级
  · **3 个或以上 `———` 才清**（视为省略号误用、归一到 `······`）
  · 不动正常的单个中点 `·`（< 3 个的中点序列保留）

注：本模块和 tomori/voice_check/ellipsis.py 在破折号策略上分流：
  - 灯：`——{2,}` 全清成 `······`（灯禁用破折号）
  - 爱音：双 `——` 保留（canon 拖音）、3+ 才清；单 `—` 保留（不动英文文本）
"""
from __future__ import annotations

import re

# 项目级 canonical 六点省略号 = 6 个 U+00B7 中点
ANON_ELLIPSIS = "······"

# 匹配所有需要被清洗的 ellipsis 变体（爱音、2026-05-10 升级——拖音）：
#   …+         - 1 个以上 U+2026 horizontal ellipsis (… / …… / ……… 都匹配)
#   \.{3,}     - 3 个以上 ASCII period (... / .... / ...... 都匹配)
#   ·{3,}      - 3 个以上中点 (·· 不动；··· / ······ / ········ 都匹配)
#   —{3,}      - **3 个以上**全角破折号 (——— 起匹配)；单 — / 双 —— 都保留
#   -{3,}      - **3 个以上**半角破折号 (--- 起匹配)；单 - / 双 -- 都保留
_ELLIPSIS_VARIANTS_RE = re.compile(
    r"…+|\.{3,}|·{3,}|—{3,}|-{3,}",
)


def normalize_ellipsis(text: str) -> tuple[str, int]:
    """把 text 中所有 ellipsis 变体清洗到 `······`。

    Returns:
        (new_text, fixed_count)
        fixed_count = 实际被改写的次数（已经是 `······` 的不计）
    """
    if not text:
        return text, 0

    fixed = 0

    def _sub(m: re.Match) -> str:
        nonlocal fixed
        matched = m.group(0)
        # 已经是 canonical form 不计 violation
        if matched == ANON_ELLIPSIS:
            return matched
        fixed += 1
        return ANON_ELLIPSIS

    new_text = _ELLIPSIS_VARIANTS_RE.sub(_sub, text)
    return new_text, fixed


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    cases = [
        # 三种 horizontal ellipsis 变体
        ("嗯…，那个…", "嗯······，那个······", 2),
        ("嗯……那个……", "嗯······那个······", 2),
        # ASCII 句点
        ("嗯...那个...", "嗯······那个······", 2),
        ("嗯......那个......", "嗯······那个······", 2),
        # 中点数量错
        ("嗯···那个····", "嗯······那个······", 2),
        ("嗯········那个", "嗯······那个", 1),  # 8 个 → 6
        # 已 canonical 不动
        ("嗯······那个······", "嗯······那个······", 0),
        # 单点 / 双点 不动
        ("嗯·那个··", "嗯·那个··", 0),
        # 单 — 保留（不动英文 dash）
        ("好啊—", "好啊—", 0),
        ("呐呐—嘛—", "呐呐—嘛—", 0),
        # 双 —— 保留（爱音 canon 拖音）
        ("嗯——那个——", "嗯——那个——", 0),
        ("好啊——可以——", "好啊——可以——", 0),
        # 3+ —— 清成 ······
        ("嗯———那个", "嗯······那个", 1),
        ("嗯———————那个", "嗯······那个", 1),
        # 半角：单/双保留、3+ 清
        ("嗯-那个--", "嗯-那个--", 0),
        ("嗯---那个", "嗯······那个", 1),
        # 混合
        ("混合：嗯…那个...还有……再加— ——和———", "混合：嗯······那个······还有······再加— ——和······", 4),
        # 空 / 无变化
        ("", "", 0),
        ("没有省略号的句子。", "没有省略号的句子。", 0),
        ("好啊~可以♪", "好啊~可以♪", 0),
    ]
    all_pass = True
    for inp, expected, exp_count in cases:
        out, n = normalize_ellipsis(inp)
        ok = (out == expected) and (n == exp_count)
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"[{status}] {inp!r:50} -> {out!r:50} fixed={n} (exp {expected!r}, exp_count={exp_count})")
    print()
    print("OVERALL:", "PASS" if all_pass else "FAIL")
