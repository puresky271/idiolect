"""实验 manifest、本地实验登记与批次可比性规则。

manifest 把一次评测的全部可变因素钉住：suite / 回复 / 标签 / scorer / adapter / 能力
的版本与内容 SHA，代码 revision（含 dirty 与工作区 diff 指纹），装配参数与最终 messages
指纹，生成参数，评测时钟，脱敏规则，以及哪些内容可精确重放、哪些不公开。密钥永不写入。

可比性（`compare_manifests`）先看**预注册的干预变量**：两份 manifest 必须声明同一组
干预变量；声明内的字段允许不同，声明外的字段（模型、夹具、时钟、scorer、标签……）一旦
不同就阻止自动池化与改善判定；任一必需字段缺失 → incomparable（不猜、不补）。
旧批次（没有 manifest 的探针产物）可以浏览，但永远是 incomparable。

登记（`ExperimentRegistry`）把 results / manifest / responses 落到同一目录，并在
manifest 里记录各文件 SHA；读取时逐一复核，任何不符（产物被改、过期审计、混臂）都
fail closed。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .. import __version__
from .tasks import canonical_sha256

MANIFEST_SCHEMA = "experiment-manifest/v1"
INTERVENTION_VARIABLES = ("prompt", "adapter", "assembly", "code", "model", "sampling", "scorer",
                          "labels", "clock", "capabilities", "suite")
# (字段路径, 标题, 所属干预组)。prompt 组的 messages 指纹在 adapter/assembly/code 干预下也允许变。
COMPARE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("suite.sha256", "suite 内容指纹", "suite"),
    ("generation.runner", "生成方式", "model"),
    ("generation.model", "模型", "model"),
    ("generation.temperature", "temperature", "sampling"),
    ("generation.max_tokens", "输出预算", "sampling"),
    ("clock.now", "评测时钟", "clock"),
    ("capabilities", "启用能力与版本", "capabilities"),
    ("adapter", "adapter 名称与版本", "adapter"),
    ("assembly_sha256", "装配参数指纹", "assembly"),
    ("prompt.messages_sha256", "最终 messages 指纹", "prompt"),
    ("scorers.source_sha256", "评分代码指纹", "scorer"),
    ("scorers.style", "风格评分器集合", "scorer"),
    ("scorers.cleaner", "clean 视图口径", "scorer"),
    ("labels.sha256", "标签指纹", "labels"),
    ("code.package_source_sha256", "包源码指纹", "code"),
)
_IMPLIES = {"code": {"prompt", "scorer"}, "adapter": {"prompt"}, "assembly": {"prompt"},
            "prompt": {"code"}}


class StaleArtifactError(RuntimeError):
    """登记目录里的产物与 manifest 记录的指纹不符：拒绝读取（fail closed）。"""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_source_sha256() -> str:
    """idiolect 包内全部源码与 package data 的合并指纹（排序后逐文件哈希）。"""
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".json", ".html") and "__pycache__" not in path.parts:
            digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
            digest.update(_file_sha256(path).encode("ascii"))
    return digest.hexdigest()


def evals_source_sha256() -> str:
    """评分相关源码（evals 子包 + 归一化 + 证据合同）的合并指纹。"""
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(_file_sha256(path).encode("ascii"))
    for extra in ("_textnorm.py", "evidence_contract.py"):
        path = root.parent / extra
        digest.update(extra.encode("utf-8"))
        digest.update(_file_sha256(path).encode("ascii"))
    return digest.hexdigest()


def code_revision() -> dict[str, Any]:
    """git revision / dirty / 工作区 diff 指纹。没有 git 或不在仓库里时如实写 unknown。"""
    root = Path(__file__).resolve().parents[2]
    out: dict[str, Any] = {"revision": "unknown", "dirty": None, "dirty_diff_sha256": None,
                           "untracked": None, "package_version": __version__,
                           "package_source_sha256": package_source_sha256()}
    if not (root / ".git").exists():
        out["source"] = "installed-package（无 git 元数据）"
        return out
    try:
        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=20, check=True).stdout
        out["revision"] = git("rev-parse", "HEAD").strip()
        status = git("status", "--porcelain")
        out["dirty"] = bool(status.strip())
        out["dirty_diff_sha256"] = hashlib.sha256(git("diff", "HEAD").encode("utf-8")).hexdigest()
        out["untracked"] = sum(1 for ln in status.splitlines() if ln.startswith("??"))
        out["source"] = "git"
    except (OSError, subprocess.SubprocessError):
        out["source"] = "git 不可用"
    return out


def _get(obj: Mapping[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def build_manifest(results: Mapping[str, Any], *, suite_raw: Mapping[str, Any], responses_raw: Any,
                   labels_raw: Any = None, intervention: list[str] | None = None,
                   intervention_note: str = "", generation: Mapping[str, Any] | None = None,
                   redaction_rules: list[str] | None = None, legacy_artifacts: list[str] | None = None) -> dict:
    """由一次 `evaluate_suite` 的结果生成 manifest（不含任何密钥）。"""
    from ..capabilities import CAPABILITIES
    from .grounding import SCORER as G_SCORER, SCORER_VERSION as G_VER
    from .matching import MATCHER_VERSION
    from .style_axis import describe_scorers

    unknown = [v for v in (intervention or []) if v not in INTERVENTION_VARIABLES]
    if unknown:
        raise ValueError(f"未知干预变量 {unknown}；可选 {INTERVENTION_VARIABLES}")
    runner = dict((results.get("responses") or {}).get("runner") or {})
    gen = {"runner": runner.get("kind", "unknown"), "model": runner.get("model"),
           "temperature": runner.get("temperature"), "max_tokens": runner.get("max_tokens"),
           "seed": runner.get("seed"), "paid": bool(runner.get("paid", False)),
           "synthetic": runner.get("synthetic")}
    if runner.get("kind") == "replay":
        gen.update(model="(replay)", temperature="(replay)", max_tokens="(replay)")
    gen.update(dict(generation or {}))
    per_task = {t["task_id"]: t["messages_sha256"] for t in results["tasks"]}
    assembly = {t["task_id"]: (suite_raw_task(suite_raw, t["task_id"]) or {}).get("assembly", {})
                for t in results["tasks"]}
    cleaners = sorted({t["record"].get("cleaner") for t in results["tasks"] if t["record"].get("present")})
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "experiment_id": results.get("experiment_id") or "",
        "intervention": {"variables": sorted(set(intervention or [])), "note": intervention_note},
        "code": code_revision(),
        "suite": {"id": results["suite"]["id"], "version": results["suite"]["version"],
                  "sha256": results["suite"]["sha256"],
                  "generated_from": suite_raw.get("generated_from"),
                  "label_source": results["suite"]["label_source"]},
        "responses": {"arm": (results.get("responses") or {}).get("arm"),
                      "sha256": (results.get("responses") or {}).get("sha256"),
                      "file_sha256": canonical_sha256(responses_raw) if responses_raw is not None else None},
        "generation": gen,
        "clock": dict(results.get("clock") or {}),
        "capabilities": [{"name": c, "version": CAPABILITIES[c].version} for c in results["capabilities"]],
        "adapter": sorted({json.dumps({k: t["adapter"].get(k) for k in ("adapter", "version")}, sort_keys=True)
                           for t in results["tasks"] if t.get("adapter")}),
        "assembly_sha256": canonical_sha256(assembly),
        "prompt": {"messages_sha256": canonical_sha256(per_task), "per_task": per_task},
        "scorers": {"grounding": {"name": G_SCORER, "version": G_VER, "matcher": MATCHER_VERSION},
                    "style": describe_scorers()["checks"], "cleaner": cleaners,
                    "source_sha256": evals_source_sha256()},
        "labels": {"sha256": canonical_sha256(labels_raw) if labels_raw else "none",
                   "human_labels_applied": len(results.get("labels_applied") or [])},
        "redaction": {"rules": list(redaction_rules or ["合成 opaque ID；无真实用户数据"]),
                      "secrets_stored": False},
        "replay": {"exact_replayable": ["suite", "responses", "labels", "messages（由代码 revision 重建）",
                                        "results（离线评分是确定性的）"],
                   "not_public": ["API key 与 base_url（从不写入）",
                                  "付费 runner 的原始响应元数据（只保留文本与 finish_reason）"]},
        "legacy_artifacts": list(legacy_artifacts or []),
        "gate": dict(results.get("gate") or {}),
    }
    return manifest


def suite_raw_task(suite_raw: Mapping[str, Any], task_id: str) -> Mapping[str, Any] | None:
    """在 suite 原始字典里按 task_id 取任务；不存在返回 None。"""
    for t in suite_raw.get("tasks", []) or []:
        if t.get("task_id") == task_id:
            return t
    return None


def compare_manifests(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict:
    """字段级可比性判定。返回 status ∈ comparable / blocked / incomparable 与逐字段理由。"""
    reasons: list[str] = []
    rows: list[dict] = []
    if left.get("schema_version") != MANIFEST_SCHEMA or right.get("schema_version") != MANIFEST_SCHEMA:
        return {"status": "incomparable", "rows": [], "pooling_allowed": False,
                "improvement_claim_allowed": False,
                "reasons": ["至少一侧没有 experiment-manifest/v1（旧批次只能浏览，不能自动比较）"]}
    iv_l = left.get("intervention", {}).get("variables")
    iv_r = right.get("intervention", {}).get("variables")
    if iv_l != iv_r:
        reasons.append(f"两侧预注册的干预变量不一致：{iv_l} vs {iv_r}")
    allowed = set(iv_l or [])
    for var in list(allowed):
        allowed |= _IMPLIES.get(var, set())
    status = "comparable" if not reasons else "blocked"
    for path, title, group in COMPARE_FIELDS:
        a, b = _get(left, path), _get(right, path)
        if a is None or b is None:
            row_status = "unknown"
            if status != "blocked":
                status = "incomparable"
            reasons.append(f"{title}（{path}）缺失：无法判断")
        elif a == b:
            row_status = "same"
        elif group in allowed:
            row_status = "different（预注册干预）"
        else:
            row_status = "different（非干预变化，阻止比较）"
            status = "blocked"
            reasons.append(f"{title} 不同但不在预注册干预里")
        rows.append({"field": path, "title": title, "group": group, "left": a, "right": b,
                     "status": row_status})
    if left.get("suite", {}).get("id") != right.get("suite", {}).get("id"):
        status = "blocked"
        reasons.append("不是同一个 suite")
    for side, m in (("left", left), ("right", right)):
        gen = m.get("generation") or {}
        if gen.get("synthetic") == "dry_run":
            status = "blocked"
            reasons.append(f"{side} 是干跑占位，不能参与比较")
    comparable = status == "comparable"
    return {"status": status, "rows": rows, "reasons": list(dict.fromkeys(reasons)),
            "pooling_allowed": comparable, "improvement_claim_allowed": comparable}


def compare_results(left: Mapping[str, Any], right: Mapping[str, Any], verdict: Mapping[str, Any]) -> dict:
    """family 级配对比较（grounding 与 style 各自独立，不合成总分）。

    只有 manifest 判定 comparable 时才给出改善/退化判断；否则列出拒绝原因、只给描述。
    """
    from .stats import sign_test

    out: dict[str, Any] = {"manifest": verdict, "axes": {}}
    for axis in ("grounding", "style"):
        a = left["aggregate"]["axes"][axis]["family_status"]
        b = right["aggregate"]["axes"][axis]["family_status"]
        improved = regressed = same = undecided = 0
        changes = []
        for fam in sorted(set(a) & set(b)):
            x, y = a[fam], b[fam]
            if x == "fail" and y == "pass":
                improved += 1
            elif x == "pass" and y == "fail":
                regressed += 1
            elif x == y and x in ("pass", "fail"):
                same += 1
            else:
                undecided += 1
            if x != y:
                changes.append({"family": fam, "left": x, "right": y})
        test = sign_test(improved, regressed)
        judgement = "refused"
        if verdict.get("improvement_claim_allowed"):
            if not test["conclusive"]:
                judgement = "inconclusive（family 数不足以显著）"
            elif test["p_improvement"] < test["alpha"]:
                judgement = "improved"
            elif test["p_regression"] < test["alpha"]:
                judgement = "regressed"
            else:
                judgement = "no_significant_change"
        out["axes"][axis] = {"improved": improved, "regressed": regressed, "same": same,
                             "undecided": undecided, "only_left": sorted(set(a) - set(b)),
                             "only_right": sorted(set(b) - set(a)), "changes": changes,
                             "sign_test": test, "judgement": judgement}
    return out


# ── 本地登记 ──────────────────────────────────────────────────────────────

def default_registry_root() -> Path:
    """实验登记根目录：`IDIOLECT_REPORT_DIR/experiments`，默认 `./report/experiments`。"""
    base = os.environ.get("IDIOLECT_REPORT_DIR", "").strip()
    return (Path(base) if base else Path.cwd() / "report") / "experiments"


def experiment_id_for(results: Mapping[str, Any]) -> str:
    """由 suite、回复集、能力与时钟指纹生成确定性的实验 ID。"""
    arm = str((results.get("responses") or {}).get("arm") or "none")
    core = canonical_sha256({"suite": results["suite"]["sha256"],
                             "responses": (results.get("responses") or {}).get("sha256"),
                             "caps": results["capabilities"], "clock": results.get("clock")})
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{results['suite']['id']}__{arm}")
    return f"{safe}__{core[:10]}"


class ExperimentRegistry:
    """本地实验登记：落盘时记录产物指纹，读取时逐一复核（不符即 fail closed）。"""
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else default_registry_root()

    def save(self, results: dict, manifest: dict, responses_raw: Any) -> Path:
        exp_id = results.get("experiment_id") or experiment_id_for(results)
        results["experiment_id"] = exp_id
        manifest["experiment_id"] = exp_id
        folder = self.root / exp_id
        folder.mkdir(parents=True, exist_ok=True)
        files = {"results.json": results, "responses.json": responses_raw}
        artifacts = {}
        for name, data in files.items():
            path = folder / name
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            artifacts[name] = _file_sha256(path)
        manifest["artifacts"] = artifacts
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        index_path = self.root / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        index = [row for row in index if row.get("experiment_id") != exp_id]
        index.append({"experiment_id": exp_id, "suite": results["suite"]["id"],
                      "arm": (results.get("responses") or {}).get("arm"),
                      "capabilities": results["capabilities"], "verdict": results["gate"]["verdict"],
                      "manifest_sha256": _file_sha256(folder / "manifest.json"), "path": exp_id})
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        return folder

    @staticmethod
    def load(folder: Path) -> tuple[dict, dict]:
        """读取并复核一个实验目录；任何指纹不符都抛 StaleArtifactError。"""
        folder = Path(folder)
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            raise StaleArtifactError(f"{folder} 没有 manifest.json：不是登记过的实验")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, sha in (manifest.get("artifacts") or {}).items():
            path = folder / name
            if not path.exists() or _file_sha256(path) != sha:
                raise StaleArtifactError(f"{folder.name}/{name} 与 manifest 登记的指纹不符（产物被改或过期）")
        if not manifest.get("artifacts"):
            raise StaleArtifactError(f"{folder.name} 的 manifest 没有登记产物指纹")
        results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
        if results.get("experiment_id") != manifest.get("experiment_id"):
            raise StaleArtifactError("results 与 manifest 的 experiment_id 不一致（混批）")
        arms = {t.get("arm_label") for t in results.get("tasks", [])}
        if len(arms) > 1:
            raise StaleArtifactError(f"results 里混有多个臂 {sorted(map(str, arms))}")
        return results, manifest


__all__ = ["COMPARE_FIELDS", "INTERVENTION_VARIABLES", "MANIFEST_SCHEMA", "ExperimentRegistry",
           "StaleArtifactError", "build_manifest", "code_revision", "compare_manifests",
           "compare_results", "default_registry_root", "experiment_id_for", "package_source_sha256"]
