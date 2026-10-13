"""证据合同：回答侧可见证据的版本化 schema、校验、序列化与安全渲染。

这是什么：调用方（上游投影、快照 adapter、评测夹具）把「这一轮允许模型看到的证据」
交给 idiolect 时用的唯一合同。它只描述**模型可见**的那一侧：

  · current / history / unknown 三态是**上游给出的投影**，idiolect 不从时间戳推导
    世界真值，也不替上游判断某条记录该算当前还是历史；
  · 评估侧的期望、禁止泄漏的值、gold answer 不属于本合同——它们放在评测任务的
    `expect` / `oracle` 里（见 `idiolect.evals.tasks`），永远不进 messages；
  · 模态字段（image / audio / location …）只标识来源，本合同只接收文本化证据，
    不做图像识别、音视频解码或地理投影。

为什么要严格：旧的无版本写法（`TemporalEvidenceContext.from_dict` 直接吃字典）会把
缺失的 status 补成 current。在评测里这等于把「上游漏标」静默变成「当前事实」，
正是要检测的那类错误被合同本身掩盖了。所以：

  · 带 `schema_version` 的输入走 `parse_evidence_context`：缺字段、未知字段、
    桶与状态不符、重复/悬空引用、时间矛盾、可见性违规、私有路径一律报错；
  · 不带版本的旧字典走兼容层：行为与旧实现一致（status 缺省为 current），但发
    `DeprecationWarning`，迁移说明见 docs/11-upgrade-guide.md。

渲染只输出白名单元数据（evidence_id、历史条目时间、安全 locator、允许的 provenance
键）。opaque locator 只是定位符，不是权限凭证。
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping

from ._textnorm import normalize_for_match

EVIDENCE_CONTEXT_SCHEMA = "evidence-context/v1"
SUPPORTED_SCHEMAS = (EVIDENCE_CONTEXT_SCHEMA,)
EVIDENCE_STATUSES = ("current", "history", "unknown")
MODALITIES = ("text", "image", "audio", "video", "location", "sensor", "document")

# 默认允许进可见文本的 provenance 键；调用方可在 permissions.render_provenance_keys 里追加。
DEFAULT_RENDER_PROVENANCE_KEYS = ("source", "modality")

# 这些键名出现在可见证据的 provenance 里就是合同错误：它们要么是评估侧信息，要么是
# 生产系统的私有定位。按下划线/连字符切词后整词匹配（`profile` 不会因含 file 误伤）。
_FORBIDDEN_KEY_TOKENS = frozenset({
    "gold", "oracle", "answer", "expected", "expectation", "label", "labels", "truth",
    "hidden", "secret", "secrets", "token", "password", "apikey", "credential",
    "credentials", "path", "filepath", "filename", "file", "sqlite", "ledger", "db",
})

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}$")
_SAFE_LOCATOR_SCHEMES = ("synthetic", "urn", "opaque", "evidence", "snapshot", "fixture")
_PRIVATE_VALUE_RE = re.compile(
    r"(?:^|[\s\"'(=])(?:[A-Za-z]:[\\/]|\\\\[\w.$-]+\\|/(?:home|Users|root|mnt|var|etc|tmp)/)"
    r"|file:/|\.\.[\\/]|\.(?:sqlite3?|db)\b",
    re.I,
)

_CONTEXT_KEYS = {"schema_version", "context_id", "observer_id", "as_of", "scene_id",
                 "permissions", "current", "history", "unknown"}
_ITEM_KEYS = {"evidence_id", "status", "text", "as_of", "valid_until", "scene_id", "modality",
              "evidence_refs", "supersedes", "visible_to", "provenance"}
_PERMISSION_KEYS = {"declared_by", "render_provenance_keys", "scopes", "note"}


class ContractError(ValueError):
    """严格解析失败。`issues` 列出全部问题，而不是遇到第一个就停。"""

    def __init__(self, issues: Iterable["ContractIssue"], schema: str = EVIDENCE_CONTEXT_SCHEMA):
        self.issues = tuple(issues)
        self.schema = schema
        head = "; ".join(f"{i.path}: {i.code}" for i in self.issues[:6])
        more = f" …（共 {len(self.issues)} 项）" if len(self.issues) > 6 else ""
        super().__init__(f"{schema} 校验失败：{head}{more}")


@dataclass(frozen=True)
class ContractIssue:
    """一条校验问题：错误码、JSON 路径、说明与严重度（error / warning）。"""
    code: str
    path: str
    message: str
    severity: str = "error"     # error | warning

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message,
                "severity": self.severity}


@dataclass(frozen=True)
class ValidationReport:
    """一次校验的全部问题；`ok` 只看 error 级。"""
    schema: str
    issues: tuple[ContractIssue, ...] = ()
    legacy: bool = False

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> tuple[ContractIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "ok": self.ok, "legacy": self.legacy,
                "issues": [i.to_dict() for i in self.issues]}


def _parse_time(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value))


def is_private_value(value: Any) -> bool:
    """看起来像本机路径、网络共享、数据库文件或目录穿越的字符串。"""
    return bool(_PRIVATE_VALUE_RE.search(str(value or "")))


def is_safe_locator(value: str) -> bool:
    """locator 是否属于允许渲染的 opaque scheme 且不像私有路径。"""
    scheme = str(value).split(":", 1)[0].lower() if ":" in str(value) else ""
    return scheme in _SAFE_LOCATOR_SCHEMES and not is_private_value(value)


def _forbidden_key(key: str) -> bool:
    low = str(key).lower()
    if "api_key" in low or "apikey" in low:
        return True
    return any(tok in _FORBIDDEN_KEY_TOKENS for tok in re.split(r"[^a-z0-9]+", low) if tok)


@dataclass(frozen=True)
class EvidenceEnvelope:
    """一条模型可见的证据。

    前七个字段与旧实现同序同默认值（旧调用 `EvidenceEnvelope("文本")` 仍成立）；
    新字段都带默认值。注意 `status` 的默认 "current" 只服务旧构造写法——严格合同
    路径要求显式给出，见 `parse_evidence_context`。
    """

    text: str
    status: str = "current"
    evidence_id: str = ""
    as_of: str | None = None
    scene_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    modality: str = "text"
    valid_until: str | None = None
    supersedes: tuple[str, ...] = ()
    visible_to: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        body = str(self.text or "").strip()
        status = str(self.status or "").strip().lower()
        if not body:
            raise ValueError("EvidenceEnvelope.text 不能为空")
        if status not in EVIDENCE_STATUSES:
            raise ValueError(
                f"EvidenceEnvelope.status 必须是 {EVIDENCE_STATUSES} 之一：{status!r}")

        def _opt(value: Any) -> str | None:
            return None if value is None else (str(value).strip() or None)

        def _tuple(value: Any) -> tuple[str, ...]:
            if isinstance(value, str):
                value = (value,)
            return tuple(str(v).strip() for v in (value or ()) if str(v).strip())

        object.__setattr__(self, "text", body)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "evidence_id", str(self.evidence_id or "").strip())
        object.__setattr__(self, "as_of", _opt(self.as_of))
        object.__setattr__(self, "scene_id", _opt(self.scene_id))
        object.__setattr__(self, "evidence_refs", _tuple(self.evidence_refs))
        object.__setattr__(self, "provenance", dict(self.provenance or {}))
        object.__setattr__(self, "modality", str(self.modality or "text").strip().lower())
        object.__setattr__(self, "valid_until", _opt(self.valid_until))
        object.__setattr__(self, "supersedes", _tuple(self.supersedes))
        object.__setattr__(self, "visible_to", _tuple(self.visible_to))

    def to_dict(self) -> dict[str, Any]:
        """稳定、可 JSON 序列化的表示（v1 条目形状，旧字段名不变）。"""
        out: dict[str, Any] = {
            "text": self.text,
            "status": self.status,
            "evidence_id": self.evidence_id,
            "as_of": self.as_of,
            "scene_id": self.scene_id,
            "evidence_refs": list(self.evidence_refs),
            "provenance": dict(self.provenance),
        }
        if self.modality != "text":
            out["modality"] = self.modality
        if self.valid_until:
            out["valid_until"] = self.valid_until
        if self.supersedes:
            out["supersedes"] = list(self.supersedes)
        if self.visible_to:
            out["visible_to"] = list(self.visible_to)
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceEnvelope":
        """旧的宽松入口：status 缺省为 current（兼容层行为，见模块 docstring）。"""
        if not isinstance(value, Mapping):
            raise TypeError("EvidenceEnvelope.from_dict 需要 mapping")
        return cls(
            text=value.get("text", ""), status=value.get("status", "current"),
            evidence_id=value.get("evidence_id", value.get("id", "")),
            as_of=value.get("as_of"), scene_id=value.get("scene_id"),
            evidence_refs=tuple(value.get("evidence_refs", ()) or ()),
            provenance=value.get("provenance", {}) or {},
            modality=value.get("modality", "text") or "text",
            valid_until=value.get("valid_until"),
            supersedes=tuple(value.get("supersedes", ()) or ()),
            visible_to=tuple(value.get("visible_to", ()) or ()),
        )


@dataclass(frozen=True)
class TemporalEvidenceContext:
    """一轮的 current/history/unknown 证据投影（模型可见侧）。

    `observer_id` / `permissions` / `context_id` 是 v1 新增的元数据：前者决定
    `visible_to` 校验，后者声明哪些额外 provenance 键允许进可见文本。它们自身不渲染。
    """

    as_of: str | None = None
    scene_id: str | None = None
    current: tuple[EvidenceEnvelope, ...] = ()
    history: tuple[EvidenceEnvelope, ...] = ()
    unknown: tuple[EvidenceEnvelope, ...] = ()
    observer_id: str | None = None
    context_id: str | None = None
    permissions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        def _opt(value: Any) -> str | None:
            return None if value is None else (str(value).strip() or None)

        object.__setattr__(self, "as_of", _opt(self.as_of))
        object.__setattr__(self, "scene_id", _opt(self.scene_id))
        object.__setattr__(self, "observer_id", _opt(self.observer_id))
        object.__setattr__(self, "context_id", _opt(self.context_id))
        object.__setattr__(self, "permissions", dict(self.permissions or {}))
        for status in EVIDENCE_STATUSES:
            rows: list[EvidenceEnvelope] = []
            for item in getattr(self, status) or ():
                envelope = item if isinstance(item, EvidenceEnvelope) else EvidenceEnvelope.from_dict(item)
                if envelope.status != status:
                    raise ValueError(
                        f"TemporalEvidenceContext.{status} 中出现 status={envelope.status!r}")
                rows.append(envelope)
            object.__setattr__(self, status, tuple(rows))

    # ── 查询 ──
    def items(self) -> tuple[EvidenceEnvelope, ...]:
        return self.current + self.history + self.unknown

    def get(self, evidence_id: str) -> EvidenceEnvelope | None:
        for item in self.items():
            if item.evidence_id == evidence_id:
                return item
        return None

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(item.evidence_id for item in self.items() if item.evidence_id)

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        refs: list[str] = []
        for item in self.items():
            for ref in item.evidence_refs:
                if ref not in refs:
                    refs.append(ref)
        return tuple(refs)

    # ── 序列化 ──
    def to_dict(self) -> dict[str, Any]:
        """旧形状（无 schema_version），保留给旧调用方；新代码用 `to_contract`。"""
        return {
            "as_of": self.as_of,
            "scene_id": self.scene_id,
            "current": [item.to_dict() for item in self.current],
            "history": [item.to_dict() for item in self.history],
            "unknown": [item.to_dict() for item in self.unknown],
            "evidence_refs": list(self.evidence_refs),
        }

    def to_contract(self) -> dict[str, Any]:
        """v1 合同形状；输出前按严格规则自检，不合格直接抛 `ContractError`。"""
        out: dict[str, Any] = {"schema_version": EVIDENCE_CONTEXT_SCHEMA}
        if self.context_id:
            out["context_id"] = self.context_id
        if self.observer_id:
            out["observer_id"] = self.observer_id
        out["as_of"] = self.as_of
        out["scene_id"] = self.scene_id
        if self.permissions:
            out["permissions"] = dict(self.permissions)
        for status in EVIDENCE_STATUSES:
            out[status] = [_strip_none(item.to_dict()) for item in getattr(self, status)]
        report = validate_evidence_context(out)
        if not report.ok:
            raise ContractError(report.errors)
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TemporalEvidenceContext":
        """带 `schema_version` 走严格合同；不带版本走旧兼容层（发 DeprecationWarning）。"""
        if not isinstance(value, Mapping):
            raise TypeError("TemporalEvidenceContext.from_dict 需要 mapping")
        if "schema_version" in value:
            return parse_evidence_context(value)
        warnings.warn(
            "无版本的证据字典走旧兼容层：缺失的 status 会按 current 处理。"
            f"新代码请写 schema_version={EVIDENCE_CONTEXT_SCHEMA!r} 并用 parse_evidence_context"
            "（迁移说明见 docs/11-upgrade-guide.md）。",
            DeprecationWarning, stacklevel=2)
        return cls(
            as_of=value.get("as_of"), scene_id=value.get("scene_id"),
            current=tuple(value.get("current", ()) or ()),
            history=tuple(value.get("history", ()) or ()),
            unknown=tuple(value.get("unknown", ()) or ()),
        )

    def render(self, *, include_provenance: bool = True) -> str:
        """生成模型可见的证据块（安全渲染，见 `render_evidence_block`）。"""
        return render_evidence_block(self, include_provenance=include_provenance)


def _strip_none(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v is not None and v != {} and v != []
            or k in ("evidence_refs",)}


# ── 严格校验 ────────────────────────────────────────────────────────────────

def validate_evidence_context(value: Any) -> ValidationReport:
    """按 v1 规则校验一个证据上下文字典，收集全部问题后返回（不抛异常）。"""
    issues: list[ContractIssue] = []

    def err(code: str, path: str, msg: str, severity: str = "error") -> None:
        issues.append(ContractIssue(code, path, msg, severity))

    if not isinstance(value, Mapping):
        err("type_error", "$", f"证据上下文必须是对象，收到 {type(value).__name__}")
        return ValidationReport(EVIDENCE_CONTEXT_SCHEMA, tuple(issues))
    version = value.get("schema_version")
    if version is None:
        err("schema_missing", "$.schema_version", f"缺少 schema_version（应为 {EVIDENCE_CONTEXT_SCHEMA!r}）")
    elif version not in SUPPORTED_SCHEMAS:
        err("schema_unknown", "$.schema_version", f"不认识的版本 {version!r}；支持 {SUPPORTED_SCHEMAS}")
        return ValidationReport(str(version), tuple(issues))

    for key in value:
        if key not in _CONTEXT_KEYS:
            err("unknown_field", f"$.{key}", f"未知字段 {key!r}")
    for key in ("context_id", "observer_id", "scene_id"):
        if value.get(key) is not None and not isinstance(value.get(key), str):
            err("type_error", f"$.{key}", f"{key} 必须是字符串")
    observer = value.get("observer_id")
    ctx_time = None
    if value.get("as_of") is not None:
        ctx_time = _check_time(value.get("as_of"), "$.as_of", err)

    render_keys: set[str] = set(DEFAULT_RENDER_PROVENANCE_KEYS)
    perms = value.get("permissions")
    if perms is not None:
        if not isinstance(perms, Mapping):
            err("type_error", "$.permissions", "permissions 必须是对象")
        else:
            for key in perms:
                if key not in _PERMISSION_KEYS:
                    err("unknown_field", f"$.permissions.{key}", f"未知字段 {key!r}")
            extra = perms.get("render_provenance_keys", [])
            if not isinstance(extra, list) or not all(isinstance(k, str) for k in extra):
                err("type_error", "$.permissions.render_provenance_keys", "必须是字符串列表")
            else:
                for key in extra:
                    if _forbidden_key(key):
                        err("forbidden_provenance_key", "$.permissions.render_provenance_keys",
                            f"{key!r} 属于评估侧或私有键，不能声明为可渲染")
                render_keys.update(extra)

    seen: dict[str, str] = {}
    supersede_refs: list[tuple[str, str]] = []
    for status in EVIDENCE_STATUSES:
        bucket = value.get(status, [])
        if bucket is None:
            bucket = []
        if not isinstance(bucket, list):
            err("type_error", f"$.{status}", f"{status} 必须是列表")
            continue
        for idx, item in enumerate(bucket):
            path = f"$.{status}[{idx}]"
            if not isinstance(item, Mapping):
                err("type_error", path, "证据条目必须是对象")
                continue
            for key in item:
                if key not in _ITEM_KEYS:
                    err("unknown_field", f"{path}.{key}", f"未知字段 {key!r}")
            for key in ("evidence_id", "status", "text"):
                if key not in item or item.get(key) in (None, ""):
                    err("missing_field", f"{path}.{key}", f"缺少必填字段 {key}")
            eid = item.get("evidence_id")
            if isinstance(eid, str) and eid:
                if not _ID_RE.match(eid):
                    err("bad_id", f"{path}.evidence_id", f"evidence_id {eid!r} 不是稳定 ID 形状")
                if eid in seen:
                    err("duplicate_id", f"{path}.evidence_id", f"{eid!r} 与 {seen[eid]} 重复")
                else:
                    seen[eid] = path
            elif eid is not None and not isinstance(eid, str):
                err("type_error", f"{path}.evidence_id", "evidence_id 必须是字符串")
            st = item.get("status")
            if isinstance(st, str) and st:
                if st not in EVIDENCE_STATUSES:
                    err("status_invalid", f"{path}.status", f"status {st!r} 不在 {EVIDENCE_STATUSES}")
                elif st != status:
                    err("status_bucket_mismatch", f"{path}.status", f"{status} 桶里出现 status={st!r}")
            if "text" in item and not isinstance(item.get("text"), str):
                err("type_error", f"{path}.text", "text 必须是字符串")
            elif isinstance(item.get("text"), str) and not item["text"].strip():
                err("missing_field", f"{path}.text", "text 不能为空白")
            modality = item.get("modality", "text")
            if not isinstance(modality, str) or modality not in MODALITIES:
                err("bad_modality", f"{path}.modality", f"modality 必须是 {MODALITIES} 之一")
            for key in ("evidence_refs", "supersedes", "visible_to"):
                raw = item.get(key, [])
                if raw is None:
                    continue
                if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
                    err("type_error", f"{path}.{key}", f"{key} 必须是字符串列表")
            for ref in item.get("evidence_refs") or []:
                if isinstance(ref, str) and is_private_value(ref):
                    err("private_locator", f"{path}.evidence_refs", f"locator {ref!r} 像本机/私有路径")
            if isinstance(eid, str):
                for ref in item.get("supersedes") or []:
                    if isinstance(ref, str):
                        supersede_refs.append((path, ref))
                        if ref == eid:
                            err("self_reference", f"{path}.supersedes", "条目不能取代自己")
            visible = item.get("visible_to") or []
            if isinstance(visible, list) and visible:
                if not observer:
                    err("observer_missing", f"{path}.visible_to",
                        "条目声明了 visible_to，但上下文没有 observer_id")
                elif observer not in visible:
                    err("visibility_violation", f"{path}.visible_to",
                        f"观察者 {observer!r} 不在 visible_to 里：不可见记录不能进可见包")
            prov = item.get("provenance", {})
            if prov is not None and not isinstance(prov, Mapping):
                err("type_error", f"{path}.provenance", "provenance 必须是对象")
            elif isinstance(prov, Mapping):
                for pk, pv in prov.items():
                    if _forbidden_key(pk):
                        err("forbidden_provenance_key", f"{path}.provenance.{pk}",
                            f"provenance 键 {pk!r} 属于评估侧或私有定位，不能进可见证据")
                    if not isinstance(pv, (str, int, float, bool)) and pv is not None:
                        err("type_error", f"{path}.provenance.{pk}", "provenance 值只能是标量")
                    elif is_private_value(pv):
                        err("private_value", f"{path}.provenance.{pk}", "provenance 值像本机/私有路径")
            item_time = None
            if item.get("as_of") is not None:
                item_time = _check_time(item.get("as_of"), f"{path}.as_of", err)
            until = None
            if item.get("valid_until") is not None:
                until = _check_time(item.get("valid_until"), f"{path}.valid_until", err)
            if ctx_time and item_time and _after(item_time, ctx_time):
                err("future_evidence", f"{path}.as_of", "条目时间晚于本轮 as_of")
            if ctx_time and until and status == "current" and _after(ctx_time, until):
                err("expired_current", f"{path}.valid_until", "条目已过有效期却标为 current")
            if item_time and until and _after(item_time, until):
                err("time_order", f"{path}.valid_until", "valid_until 早于 as_of")
            sid = item.get("scene_id")
            if sid and value.get("scene_id") and sid != value.get("scene_id"):
                err("scene_differs", f"{path}.scene_id",
                    "条目来自其他场景（允许，但请确认观察者确实见过）", "warning")
    for path, ref in supersede_refs:
        if ref not in seen:
            err("dangling_ref", f"{path}.supersedes", f"引用的 {ref!r} 不在本上下文里")
    return ValidationReport(EVIDENCE_CONTEXT_SCHEMA, tuple(issues))


def _check_time(value: Any, path: str, err) -> datetime | None:
    try:
        parsed = _parse_time(value)
    except (TypeError, ValueError):
        err("bad_time", path, f"{value!r} 不是 ISO 8601 时间")
        return None
    if parsed is None or parsed.tzinfo is None:
        err("bad_time", path, f"{value!r} 缺少时区（严格合同要求带 UTC 偏移）")
        return None
    return parsed


def _after(a: datetime, b: datetime) -> bool:
    return a > b


def parse_evidence_context(value: Any) -> TemporalEvidenceContext:
    """严格解析 v1 证据上下文；任何 error 级问题都抛 `ContractError`。"""
    report = validate_evidence_context(value)
    if not report.ok:
        raise ContractError(report.errors)
    def rows(status: str) -> tuple[EvidenceEnvelope, ...]:
        return tuple(EvidenceEnvelope.from_dict(item) for item in (value.get(status) or []))
    return TemporalEvidenceContext(
        as_of=value.get("as_of"), scene_id=value.get("scene_id"),
        current=rows("current"), history=rows("history"), unknown=rows("unknown"),
        observer_id=value.get("observer_id"), context_id=value.get("context_id"),
        permissions=value.get("permissions") or {},
    )


def coerce_temporal_evidence_context(
    value: TemporalEvidenceContext | Mapping[str, Any] | None,
) -> TemporalEvidenceContext | None:
    """把对象、v1 合同字典或旧字典统一成 `TemporalEvidenceContext`。"""
    if value is None:
        return None
    if isinstance(value, TemporalEvidenceContext):
        return value
    return TemporalEvidenceContext.from_dict(value)


# ── 渲染 ─────────────────────────────────────────────────────────────────

_LABELS = {"current": "当前证据", "history": "历史证据", "unknown": "未知边界"}
_GUIDE = ("（当前证据可以直接用；历史证据只说明过去，提到时带上时间；"
          "未知边界里的事不要编，也不要说成已经被否定。）")


def render_evidence_block(context: TemporalEvidenceContext, *, include_provenance: bool = True) -> str:
    """把证据投影渲染成模型可见文本，只输出白名单元数据。

    输出：头 + as_of/scene_id + 一行用法说明 + 三个分节。每条：`- <id>[ 时间]: 正文`，
    后附安全 locator 与允许的 provenance 键。不渲染：observer_id、visible_to、
    permissions、supersedes 以外的内部字段、任何被禁止或未声明的 provenance 键、
    看起来像私有路径的 locator（以 `<redacted>` 代替，校验报告会单独记一条错误）。
    """
    allowed = set(DEFAULT_RENDER_PROVENANCE_KEYS)
    extra = context.permissions.get("render_provenance_keys") if context.permissions else None
    if isinstance(extra, (list, tuple)):
        allowed.update(str(k) for k in extra)
    lines = ["【时空证据上下文】"]
    if context.as_of:
        lines.append(f"as_of: {context.as_of}")
    if context.scene_id:
        lines.append(f"scene_id: {context.scene_id}")
    lines.append(_GUIDE)
    for status in EVIDENCE_STATUSES:
        lines.append(f"[{_LABELS[status]}]")
        items = getattr(context, status)
        if not items:
            lines.append("- （无）")
            continue
        for item in items:
            head = item.evidence_id or ""
            if status == "history" and item.as_of:
                head = f"{head} [as_of: {item.as_of}]" if head else f"[as_of: {item.as_of}]"
            if item.supersedes:
                head += f" [更正: {', '.join(item.supersedes)}]"
            line = f"- {head}: {item.text}" if head else f"- {item.text}"
            refs = [ref if is_safe_locator(ref) else "<redacted>" for ref in item.evidence_refs]
            if refs:
                line += f" [evidence_refs: {', '.join(refs)}]"
            if include_provenance and item.provenance:
                shown = [
                    f"{key}={item.provenance[key]}" for key in sorted(item.provenance)
                    if key in allowed and not _forbidden_key(key)
                    and not is_private_value(item.provenance[key])
                ]
                if shown:
                    line += f" [provenance: {', '.join(shown)}]"
            lines.append(line)
    return "\n".join(lines)


def find_forbidden_values(messages: Any, values: Iterable[str]) -> list[str]:
    """在 messages（或纯文本）里找评估侧禁止出现的值；按 `_textnorm` 口径匹配。"""
    if isinstance(messages, str):
        haystack = messages
    else:
        haystack = "\n".join(str(m.get("content", "")) for m in (messages or []) if isinstance(m, Mapping))
    norm = normalize_for_match(haystack)
    hits: list[str] = []
    for value in values or ():
        needle = normalize_for_match(value)
        if needle and needle in norm and value not in hits:
            hits.append(value)
    return hits


# 研究文档可用更短的名称引用同一个纯文本投影合同。
KnowledgeProjection = TemporalEvidenceContext

__all__ = [
    "EVIDENCE_CONTEXT_SCHEMA", "SUPPORTED_SCHEMAS", "EVIDENCE_STATUSES", "MODALITIES",
    "DEFAULT_RENDER_PROVENANCE_KEYS", "ContractError", "ContractIssue", "ValidationReport",
    "EvidenceEnvelope", "TemporalEvidenceContext", "KnowledgeProjection",
    "coerce_temporal_evidence_context", "find_forbidden_values", "is_private_value",
    "is_safe_locator", "parse_evidence_context", "render_evidence_block",
    "validate_evidence_context",
]
