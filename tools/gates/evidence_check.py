"""证据一致性校验（evidence gate）：回复里的自我断言与称呼是否与 canon / voice 一致。

为什么存在（2026-09-13，Ditto 方法论移植）：WikiRoleEval 用「黄金证据」让评判 LLM
检验回复与角色知识是否一致；本仓库不走 LLM judge，改走**机械投影**——canon / voice
里本来就写死了五套可检验事实（乐队担当、就读学校、CRYCHIC 成员资格）与一张称呼表
（NICKNAME_RULE / 【关系差异】），把它们收拢成表，逐句扫描回复中的自我断言与称呼，
偏离即记违规。`tests/test_oob_evidence_gates.py` 的 SSOT 投影测试保证：角色包改了
事实或称呼，这张表不改就会红。

两档语义：
  · fact 档（role / school / crychic）：**与角色包明文事实矛盾**，--gate 任一命中即 rc 1。
    只查**专属**词：通用乐器活动不查（「弹吉他」爱音/乐奈都可能合法说出；
    素世说「我弹吉他」属于漏报，是有意的取舍——非专属词的误报率撑不起门禁）。
  · address 档（称呼）：偏离本角色 NICKNAME_RULE 的互称。出站清洗会改写一部分称呼
    （立希把「乐奈」收成「野猫」等），线上口径与本闸共用一张表；默认只记账，
    --strict 才判死。

已知取舍（诚实记录）：
  · 否定句不报（「我不是鼓手」）——守卫是「关键词前 3 字内有否定词则跳过该子句」。
  · 自称检查（我/僕/私）不在本模块：style_target 层已有可检验数字，口径不重复。
  · 表是手工收拢的（来源见每条注释），不是蒸馏产物——所以不做 --no-exemplars 那套。

用法：
  py -X utf8 tools/gates/evidence_check.py                  # 无参 = 内置 ground-truth 自检（离线，进 offline_smoke）
  py -X utf8 tools/gates/evidence_check.py --label run1     # 扫 report/{probe,oob,multiturn}_run1.jsonl
  py -X utf8 tools/gates/evidence_check.py --label run1 --gate --strict
"""
from __future__ import annotations

# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from _paths import REPORT  # noqa: E402


# ════════════════════════════════════════════════════════════════
# 事实表（SSOT 投影：每一条都必须能在对应角色包源文件里找到，契约测试在钉）
# ════════════════════════════════════════════════════════════════

# 乐队专属担当词（来源：各角色 canon.py 的「乐队 / 担当」行）。
# 只收**专属**词——「吉他」为爱音/乐奈共享，不收。
EXCLUSIVE_ROLES: dict[str, tuple[str, ...]] = {
    "anon": ("节奏吉他",),
    "tomori": ("主唱", "作词"),
    "taki": ("鼓手", "打鼓", "作曲"),
    "soyo": ("贝斯手", "贝斯"),
    "rana": ("主音吉他",),
}

# 就读学校（来源：各角色 canon.py 的「学校：」行）
SCHOOL_OF: dict[str, tuple[str, ...]] = {
    "羽丘": ("anon", "tomori"),
    "月之森": ("soyo",),
    "花咲川": ("taki", "rana"),
}

# CRYCHIC 成员（canon：灯/立希/素世；乐奈只在重组商讨现场出现、爱音后加入 MyGO）
CRYCHIC_MEMBERS = frozenset({"tomori", "taki", "soyo"})

# 专属称呼表（来源：各角色 voice.py 的 NICKNAME_RULE / 【关系差异】）。
# 只收**专属**形式；直呼本名对所有人合法，不进表。
ALLOWED_NICKS: dict[str, frozenset[str]] = {
    "anon": frozenset({"soyorin", "rikki", "灯灯", "小乐奈"}),
    "tomori": frozenset({"小爱", "小素世", "小立希", "小乐奈"}),
    "soyo": frozenset({"小爱音", "小灯", "小立希", "小乐奈", "小睦"}),
    "taki": frozenset({"野猫"}),
    "rana": frozenset({"rikki"}),
}
_ALL_NICKS = sorted({n for s in ALLOWED_NICKS.values() for n in s}, key=len, reverse=True)

# 明文禁用的直呼（canon 写死的否定句式）
FORBIDDEN_PLAIN: dict[str, tuple[str, ...]] = {
    "rana": ("立希",),  # rana/voice.py：不要叫「立希」——你从不那么叫她
}


# ════════════════════════════════════════════════════════════════
# 检测
# ════════════════════════════════════════════════════════════════

_RX_CLAIM = re.compile(
    r"(我是|我就是|我当|我担任|我负责|我担当|我来打|我来弹|我来唱|我打的是|我弹的是|"
    r"我唱的是|归我|由我|我的担当|我在乐队|乐队里我|负责|担当)")
# 学校断言的动词面更宽：「我在羽丘上学」这类句式不含「我是」
_RX_SCHOOL_CLAIM = re.compile(r"(我在|我就读|我是|我上学|我的学校)")
_RX_NEGATION = re.compile(r"(不是|并非|没有|并没|不算|谈不上|别叫|不叫|不再是|没当|没有当)")
_RX_CRYCHIC_MEMBER_CLAIM = re.compile(r"我(?:是|曾是|曾经是|曾经在|曾经|在.{0,4}担任|在.{0,4}当)")


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"[。！？!?\n；;，,]", text) if c.strip()]


def _negated_before(clause: str, idx: int) -> bool:
    """关键词前 3 字内有否定词 → 该子句按否定句处理，不报。"""
    return bool(_RX_NEGATION.search(clause[max(0, idx - 3):idx]))


def _detect_nicks(text: str) -> list[str]:
    """命中的专属称呼（长词优先并遮蔽，避免「小爱」误吃「小爱音」）。"""
    masked = text
    found = []
    lowered = masked.lower()
    for nick in _ALL_NICKS:
        low = nick.lower()
        if low in lowered:
            found.append(nick)
            # 大小写不敏感地遮蔽拉丁词；中文词直接替换
            masked = re.sub(re.escape(nick), "□" * len(nick), masked, flags=re.IGNORECASE)
            lowered = masked.lower()
    return found


@dataclass
class EvidenceResult:
    violations: list[dict] = field(default_factory=list)

    @property
    def fact_violation(self) -> bool:
        return any(v["kind"] in ("role", "school", "crychic") for v in self.violations)

    @property
    def passed(self) -> bool:
        return not self.violations


def audit_evidence(reply: str, char: str) -> EvidenceResult:
    """对单条回复做证据一致性校验。未知角色 → 只跳过（表按角色 key 建索引）。"""
    text = str(reply or "").strip()
    if not text or char not in EXCLUSIVE_ROLES:
        return EvidenceResult()
    out: list[dict] = []

    for clause in _clauses(text):
        low_clause = clause.lower()
        # 1) 专属担当：子句含他人专属词 + 自我断言动词（否定守卫）
        if _RX_CLAIM.search(clause):
            for other, kws in EXCLUSIVE_ROLES.items():
                if other == char:
                    continue
                hit = None
                for kw in kws:
                    idx = low_clause.find(kw.lower())
                    if idx >= 0 and not _negated_before(clause, idx):
                        hit = kw
                        break
                if hit:
                    out.append({"kind": "role",
                                "detail": f"{char} 声称担当「{hit}」（{other} 的专属担当）",
                                "sample": clause[:40]})
                    break
        # 2) 学校
        if _RX_SCHOOL_CLAIM.search(clause):
            for school, allowed in SCHOOL_OF.items():
                idx = clause.find(school)
                if idx < 0 or char in allowed:
                    continue
                if _negated_before(clause, idx):
                    continue
                out.append({"kind": "school", "detail": f"{char} 声称就读「{school}」",
                            "sample": clause[:40]})
                break
        # 2b) 乐奈的年级（花咲川初中部；自称「高中生/高等部」即矛盾）
        if char == "rana" and "花咲川" in clause and re.search(r"(高中|高等部)", clause):
            idx = clause.find("花咲川")
            if _RX_SCHOOL_CLAIM.search(clause) and not _negated_before(clause, idx):
                out.append({"kind": "school", "detail": "乐奈是花咲川初中三年级，不是高中生",
                            "sample": clause[:40]})
        # 3) CRYCHIC 成员资格
        if "crychic" in low_clause and char not in CRYCHIC_MEMBERS:
            if _RX_CRYCHIC_MEMBER_CLAIM.search(clause) and not _negated_before(
                    clause, low_clause.find("crychic")):
                out.append({"kind": "crychic", "detail": f"{char} 声称是 CRYCHIC 成员",
                            "sample": clause[:40]})
        # 4) 专属称呼
        for nick in _detect_nicks(clause):
            if nick not in ALLOWED_NICKS[char] and nick.lower() not in ALLOWED_NICKS[char]:
                out.append({"kind": "address",
                            "detail": f"{char} 使用了非本角色的专属称呼「{nick}」",
                            "sample": clause[:40]})
        # 5) 明文禁用的直呼
        for plain in FORBIDDEN_PLAIN.get(char, ()):
            idx = clause.find(plain)
            if idx >= 0 and not _negated_before(clause, idx):
                out.append({"kind": "address",
                            "detail": f"{char} 直呼「{plain}」——canon 明文不用这个称呼",
                            "sample": clause[:40]})
    return EvidenceResult(violations=out)


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

_GOOD = [
    ("爱音", "我是MyGO的节奏吉他手，在羽丘上学。"),
    ("灯", "我负责主唱和作词。"),
    ("立希", "鼓归我打，作曲也在做。"),
    ("素世", "我是贝斯手，月之森的学生。"),
    ("乐奈", "我是MyGO的主音吉他手。"),
    ("灯", "我曾在CRYCHIC担任主唱。"),
    ("素世", "我不是鼓手，鼓是立希的。"),
    ("乐奈", "我不叫她立希。"),
    ("爱音", "rikki和soyorin都在哦。"),
    ("灯", "小立希和小素世……嗯。"),
    ("素世", "小立希也在的。"),
    ("立希", "野猫又溜了。"),
]
_BAD = [
    ("素世", "我负责打鼓，节奏感是我最强的。", "role"),
    ("立希", "我是贝斯手，低音是我的语言。", "role"),
    ("灯", "我在乐队里弹主音吉他。", "role"),
    ("爱音", "我是MyGO的主音吉他手。", "role"),
    ("乐奈", "我是主唱。", "role"),
    ("立希", "我在羽丘上学，跟灯同班。", "school"),
    ("乐奈", "我在羽丘上学。", "school"),
    ("爱音", "我的学校是月之森。", "school"),
    ("乐奈", "我是花咲川的高中生。", "school"),
    ("爱音", "我曾是CRYCHIC的成员。", "crychic"),
    ("乐奈", "我是CRYCHIC的吉他手。", "crychic"),
    ("立希", "soyorin今天没来排练。", "address"),
    ("灯", "rikki……刚才说到哪了。", "address"),
    ("素世", "小爱今天也很吵呢。", "address"),
    ("爱音", "小爱也在吗？", "address"),
    ("乐奈", "立希知道怎么办。", "address"),
]

_CHARKEY = {"爱音": "anon", "灯": "tomori", "立希": "taki", "素世": "soyo", "乐奈": "rana"}


def _selftest() -> int:
    fp = [(c, t) for c, t in _GOOD if audit_evidence(t, _CHARKEY[c]).violations]
    blind = [(c, want) for c, t, want in _BAD
             if want not in {v["kind"] for v in audit_evidence(t, _CHARKEY[c]).violations}]
    print(f"[evidence_check] 自检：好样本 {len(_GOOD)}（误报 {len(fp)}）｜"
          f"坏样本 {len(_BAD)}（盲区 {blind if blind else '无'}）")
    for c, t in fp:
        print(f"  误报：{c}｜{t!r} → {audit_evidence(t, c).violations}")
    if fp or blind:
        print("[evidence_check] FAIL")
        return 1
    print("[evidence_check] PASS")
    return 0


def _resolve_jsonl(label: str, kind: str):
    kinds = [kind] if kind != "auto" else ["probe", "oob", "multiturn"]
    for k in kinds:
        p = REPORT / f"{k}_{label}.jsonl"
        if p.exists():
            return p
    raise FileNotFoundError(f"report/ 下找不到 {kinds} 前缀的 {label}.jsonl——先跑对应探针")


def _scan(label: str, kind: str, gate: bool, strict: bool) -> int:
    path = _resolve_jsonl(label, kind)
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    stat: dict[str, dict] = defaultdict(lambda: {"n": 0, "fact": 0, "address": 0})
    samples: list[str] = []
    for r in rows:
        if not r.get("reply") or r.get("error"):
            continue
        char = _CHARKEY.get(r.get("char", ""), r.get("char", ""))
        s = stat[char]
        s["n"] += 1
        res = audit_evidence(r["reply"], char)
        for v in res.violations:
            # 违规级计数：fact 三类合一判死，address 单独记账
            s["fact" if v["kind"] in ("role", "school", "crychic") else "address"] += 1
            if len(samples) < 8:
                samples.append(f"{r.get('char')}|{r.get('scenario', '')}: {v['detail']}｜{v['sample']!r}")
    fact_total = sum(s["fact"] for s in stat.values())
    addr_total = sum(s["address"] for s in stat.values())
    print(f"[evidence_check] {path.name}：fact 违规 {fact_total} 条｜address 偏离 {addr_total} 条")
    for char in sorted(stat):
        s = stat[char]
        print(f"  {char}：n={s['n']} fact={s['fact']} address={s['address']}")
    for x in samples:
        print(f"  · {x}")
    if not stat:
        print("[evidence_check] 零有效回复——缺证据不算通过")
        return 2
    if gate:
        if fact_total or (strict and addr_total):
            print(f"[evidence_check] FAIL：fact={fact_total}"
                  + (f"（--strict 下 address={addr_total} 也计）" if strict else ""))
            return 1
        print("[evidence_check] PASS：无 fact 违规" + ("（address 偏离已记账）" if addr_total else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    ap.add_argument("--kind", default="auto", choices=["auto", "probe", "oob", "multiturn"])
    ap.add_argument("--gate", action="store_true", help="fact 违规即 rc 1")
    ap.add_argument("--strict", action="store_true", help="address 档也参与判定")
    args = ap.parse_args()
    if not args.label:
        return _selftest()
    try:
        return _scan(args.label, args.kind, args.gate, args.strict)
    except FileNotFoundError as exc:
        print(f"[evidence_check] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
