"""上下文工作区：四层 prompt 在真实聊天系统里的「前后文骨架」。

每一轮要做的事是：把十几路候选材料（状态帧、记忆召回、事实卡、八卦、
认知指令……）全部收集成「工作区」，打分排序、按预算裁剪，再按**固定层序**
装配成 messages。本模块提供这套结构的两块通用骨架：

1. **装配骨架**（`ContextWorkspace` + `assemble`）：12 层固定顺序、空块剔除、
   整体预算尾裁、执行包追加到最后一条 user 消息末尾。
2. **事实选择器**（`select_facts`）：候选事实 → 词汇重叠 + 新近度 + 渠道/类型
   加权 → 阈值过滤 → 近去重 → 条数与字符双预算。打分公式与权重是
   实测调校值（各常量的出处见下方注释）。

**本模块未收录的部分**（各自依赖更大的系统，见 docs/08-context-workspace.md）：
语义向量通道（要 bge-m3）、纠偏取代、注入记账、级联折叠、生命周期卡。

与四层的关系：四层回答「这个角色该怎么说话」，工作区回答「这一轮还该让模型
知道什么」。`build_workspace_messages` 把四层放在 persona 位（首层、不可裁剪），
调用方把记忆/日程/世界状态等块挂进其余层位即可。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .assemble import build_system_prompt

# 设计理由：稳定前缀在前（缓存命中），动态上下文居中，
# 执行指令不单独成块、而是贴到最后一条 user 之后（离生成端最近，最不容易被稀释）。
LAYER_ORDER = (
    "persona",                 # 人格 prompt（idiolect 四层放这里）
    "historical_recap",        # 历史聊天摘要
    "current_state",           # 角色当前状态帧（位置/日程/天气/心情）
    "interlocutor_state",      # 对话方状态帧
    "proactive_continuity",    # 主动连续性（上次说到哪、待续的话头）
    "fact_workspace",          # 事实工作区（select_facts 的产出写这里）
    "memory_recall",           # 记忆召回
    "cluster_memory",          # 聚类记忆
    "conversation_arc",        # 对话弧线（本场对话的阶段/走向）
    "on_demand_evidence",      # 按需证据（用户问起才查的细节）
    "cognitive",               # 认知指令
    "recent_dialogue_guard",   # 最近对话护栏（防复读/防矛盾）
)


@dataclass(frozen=True)
class ContextBlock:
    key: str
    text: str
    pinned: bool = False       # pinned 的块不参与预算裁剪（persona 默认 pinned）


class ContextWorkspace:
    """一轮对话的上下文工作区：按固定层序收块，再整体装配成 messages。"""

    def __init__(self) -> None:
        self._blocks: dict[str, ContextBlock] = {}

    def add(self, key: str, text: str, *, pinned: bool = False) -> "ContextWorkspace":
        """挂入一个上下文块。空文本直接忽略（层不存在比空层好）。"""
        body = str(text or "").strip()
        if not body:
            return self
        self._blocks[str(key)] = ContextBlock(str(key), body, pinned)
        return self

    def texts(self) -> dict[str, str]:
        return {key: block.text for key, block in self._blocks.items()}

    def _ordered_keys(self) -> list[str]:
        known = [key for key in LAYER_ORDER if key in self._blocks]
        custom = [key for key in self._blocks if key not in LAYER_ORDER]
        return known + custom  # 自定义层排在 12 层之后、对话历史之前

    def assemble(
        self,
        *,
        history: list[dict] | None = None,
        execution_packet: str = "",
        max_chars: int = 0,
    ) -> list[dict]:
        """装配 messages：system 块按层序 → 对话历史 → 执行包贴**已装配的最后一条 user**。

        `max_chars` > 0 时做整体预算裁剪：从层序尾部开始整块摘除未 pinned 的块，
        直到 system 总量达标。不切块内文本——切半块上下文比整块缺失更难排查。

        注意 `execution_packet` 的作用对象：它贴的是**这里已有**的最后一条 user，
        也就是历史里的上一轮。本轮那句话还没进 messages（通常由调用方随后 append），
        所以「把执行包放到离生成端最近的位置」这件事，`build_workspace_messages`
        会自己处理——它在 append 本轮 user 时贴上。这里不传 packet 就对了。

        给了 packet 却没有可贴的 user 时**直接报错**：静默丢弃会让「模型没遵守执行
        指令」变成一个查不出来的现象（这条是踩过的坑）。
        """
        keys = self._ordered_keys()
        if max_chars > 0:
            def _total(ks: list[str]) -> int:
                return sum(len(self._blocks[k].text) for k in ks)
            for key in reversed(keys):
                if _total(keys) <= max_chars:
                    break
                if not self._blocks[key].pinned:
                    keys.remove(key)

        messages: list[dict] = [
            {"role": "system", "content": self._blocks[key].text} for key in keys
        ]
        for raw in history or []:
            if not isinstance(raw, dict):
                continue
            role = str(raw.get("role", "") or "").strip().lower()
            content = str(raw.get("content", "") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        packet = str(execution_packet or "").strip()
        if packet:
            for idx in range(len(messages) - 1, -1, -1):
                if messages[idx].get("role") == "user":
                    messages[idx]["content"] = (
                        str(messages[idx].get("content", "") or "").rstrip() + "\n\n" + packet
                    )
                    break
            else:
                raise ValueError(
                    "execution_packet 没有可贴的 user 消息（history 里没有 user）。\n"
                    "本轮那句话还没进 messages 时，请不要在这里传 packet：\n"
                    "  · 用 build_workspace_messages(...) 的 execution_packet 参数，它会贴到本轮 user 上；\n"
                    "  · 或自己 append 本轮 user 之后再贴。\n"
                    "静默丢弃执行指令是不允许的——那会让「模型没遵守」变成查不出来的现象。"
                )
        return messages


def build_workspace_messages(
    char: str,
    user_text: str,
    *,
    blocks: list[tuple[str, str]] | None = None,
    history: list[dict] | None = None,
    execution_packet: str = "",
    session_id: str | None = None,
    include_turn_logic: bool = True,
    max_chars: int = 0,
    now=None,
) -> list[dict]:
    """一行入口：idiolect 四层进 persona 位，外部块挂其余层，装配成 messages。

    `blocks` 为 `(层名, 文本)` 列表；层名见 `LAYER_ORDER`，自定义名排在 12 层后。

    `execution_packet`（本轮执行指令：长度预算、风格提醒）**贴在本轮 user 消息末尾**
    ——那是模型真正要回答的那条，也是离生成端最近的位置。贴完的 messages 形如
    `[system…, user(上一轮), assistant, user(本轮 + 执行包)]`。
    """
    ws = ContextWorkspace()
    persona = build_system_prompt(
        char, user_text, session_id=session_id,
        include_turn_logic=include_turn_logic, now=now)
    ws.add("persona", persona, pinned=True)
    for key, text in blocks or []:
        if key == "persona":
            continue  # persona 位只允许 idiolect 四层，外部块请挂其余层
        ws.add(key, text)

    # packet 由这里贴到本轮 user 上，所以不给 assemble 传（它只会贴到历史里那条 user）。
    messages = ws.assemble(history=history, max_chars=max_chars)

    current = str(user_text or "").rstrip()
    packet = str(execution_packet or "").strip()
    if packet:
        current = f"{current}\n\n{packet}" if current else packet
    messages.append({"role": "user", "content": current})
    return messages


# ── 事实选择器 ─────────────────────────────────────────────────────────────
#
# 以下常量全部是实测调校值。
# 词表：通用时间词是路由信号，不是话题证据——连同分词器可能切出的
# 2/3-gram 一起排除，否则长 CJK 串会通过子串把它们带回来。
_STOP_TOKENS = {
    "你", "我", "他", "她", "它", "青空", "访客", "用户", "角色", "之前", "刚才", "现在",
    "今天", "这个", "那个", "到底", "怎么", "什么", "时候", "记得", "说过", "还是",
    "已经", "一下", "一个", "的话", "那么", "然后", "可以", "不是", "不要", "回应",
    "这几天", "这几", "几天", "最近", "刚刚", "明天", "昨天", "前天", "后天", "上次",
    "上周", "下周", "这周", "本周", "早上", "晚上", "中午", "下午", "学校",
}

# 强弱重叠边界（2026-08-16 事实工作区审计 finding 2.2）：
# 单个共享 bigram 得分 min(4,2)/2 + 0.65 = 1.65，一个 trigram 2.15。
# 低于阈值保留参选资格，但拿不到任何加权——泛词碰撞不许靠
# 渠道/类型/stacked bonus 混进前排。
_MIN_LEXICAL_OVERLAP = 2.0

_KIND_BONUS = {"correction": 9.0, "commitment": 6.5, "open_thread": 5.0, "fact": 1.0}

# 渠道加权（2026-07-27 审计调校：memory_recall 曾低到 0.2，
# 真实日志里 0/10 条记忆能被选中，提到 0.8 后恢复竞争力）。
_CHANNEL_BONUS = {
    "turn_fact": 2.0, "today_fact": 1.6, "schedule_recall": 2.2,
    "historical_recap": 0.8, "daily_continuity": 1.0, "memory_recall": 0.8,
    "user_profile": 0.5, "relation_reflection": 0.6, "kairos_brief": 0.5,
    "gossip": -0.2, "assistant_history": 1.0, "visual_history": 0.8,
    "scratchpad": 0.1, "external_evidence": 0.3,
}


@dataclass(frozen=True)
class FactRecord:
    """一条候选事实。`kind` ∈ fact / commitment / open_thread / correction。"""

    text: str
    kind: str = "fact"
    channel: str = "turn_fact"
    created_at_ms: int = 0


def topic_tokens(value: str) -> set[str]:
    """话题词表：英文词原样收录，CJK 串切 2/3-gram（≤4 字的整词也收）。"""
    text = re.sub(r"https?://\S+", " ", str(value or "").lower())
    tokens: set[str] = set()
    for word in re.findall(r"[a-z0-9_\-]{2,}|[一-鿿]{2,}", text):
        if word in _STOP_TOKENS:
            continue
        if re.fullmatch(r"[一-鿿]+", word):
            if len(word) <= 4:
                tokens.add(word)
            for size in (2, 3):
                for idx in range(max(0, len(word) - size + 1)):
                    gram = word[idx:idx + size]
                    if gram not in _STOP_TOKENS:
                        tokens.add(gram)
        else:
            tokens.add(word)
    return tokens


def overlap_score(query_tokens: set[str], text: str) -> float:
    """查询与一条事实的词汇重叠分（0 ~ 12）。"""
    if not query_tokens:
        return 0.0
    record_tokens = topic_tokens(text)
    if not record_tokens:
        return 0.0
    shared = query_tokens & record_tokens
    if not shared:
        return 0.0
    weighted = sum(min(4, len(token)) for token in shared)
    return min(12.0, weighted / 2.0 + len(shared) * 0.65)


def recency_score(newest_ts: int, ts: int) -> float:
    """新近度六档：相对候选集里最新记录的年龄（15 分钟内 2.5 → 两周以上 0.1）。"""
    if newest_ts <= 0 or ts <= 0:
        return 0.0
    age_ms = max(0, newest_ts - ts)
    hour = 60 * 60 * 1000
    day = 24 * hour
    if age_ms <= 15 * 60 * 1000:
        return 2.5
    if age_ms <= 6 * hour:
        return 2.0
    if age_ms <= day:
        return 1.5
    if age_ms <= 3 * day:
        return 1.0
    if age_ms <= 14 * day:
        return 0.5
    return 0.1


def _norm_text(value: str) -> str:
    return re.sub(r"\W+", "", str(value or "").lower())


def select_facts(
    query: str,
    records: list[FactRecord] | list[dict],
    *,
    max_records: int = 10,
    max_chars: int = 3200,
) -> list[dict]:
    """从候选事实里选出这一轮该注入的若干条。

    流程：逐条打分（重叠 + 新近度 + 渠道/类型加权）→ 零重叠淘汰、弱重叠去权
    → 降序 → 近去重 → 条数预算 → 字符预算。返回 `[{"text", "kind", "channel",
    "score"}, ...]`，可直接拼进 `fact_workspace` 层。
    """
    rows: list[dict] = []
    for raw in records or []:
        if isinstance(raw, FactRecord):
            row = {"text": raw.text, "kind": raw.kind,
                   "channel": raw.channel, "created_at_ms": raw.created_at_ms}
        else:
            row = dict(raw)
        row["text"] = str(row.get("text", "") or "").strip()
        if row["text"]:
            rows.append(row)

    query_tokens = topic_tokens(str(query or ""))
    newest_ts = max((int(row.get("created_at_ms", 0) or 0) for row in rows), default=0)
    for row in rows:
        kind = str(row.get("kind", "") or "fact")
        channel = str(row.get("channel", "") or "turn_fact")
        overlap = overlap_score(query_tokens, row["text"])
        recency = recency_score(newest_ts, int(row.get("created_at_ms", 0) or 0))
        score = overlap + recency
        if overlap >= _MIN_LEXICAL_OVERLAP:
            score += _KIND_BONUS.get(kind, 1.0) + _CHANNEL_BONUS.get(channel, 0.0)
        row["score"] = round(score, 3)
        row["_overlap"] = overlap

    ranked = sorted(
        (row for row in rows if row["_overlap"] > 0.0),
        key=lambda row: row["score"], reverse=True)

    selected: list[dict] = []
    seen: set[str] = set()
    total_chars = 0
    for row in ranked:
        norm = _norm_text(row["text"])
        if not norm or norm in seen:
            continue
        if len(selected) >= max_records:
            break
        if total_chars + len(row["text"]) > max_chars:
            continue
        seen.add(norm)
        total_chars += len(row["text"])
        selected.append({
            "text": row["text"], "kind": str(row.get("kind", "") or "fact"),
            "channel": str(row.get("channel", "") or "turn_fact"),
            "score": row["score"],
        })
    return selected


__all__ = [
    "LAYER_ORDER", "ContextBlock", "ContextWorkspace", "FactRecord",
    "build_workspace_messages", "overlap_score", "recency_score",
    "select_facts", "topic_tokens",
]
