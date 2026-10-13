"""grounding 与适用性契约：每条断言对应一种「把缺测/空白/误判当通过」的方式。

全部走内置 suite 与合成回放（只测链路，不是模型能力），零密钥、零网络。
"""
from __future__ import annotations

import copy
import os
import unittest
from unittest import mock

from idiolect.evals.pipeline import evaluate_suite, load_response_set
from idiolect.evals.suites import load_responses, load_suite, read_json_source


def _run(suite_name, replay, caps, edit=None):
    suite = load_suite(suite_name)
    raw = copy.deepcopy(read_json_source(replay)) if not replay.startswith("builtin:long") else None
    if raw is None:
        responses = load_responses(replay, suite)
    else:
        if edit:
            edit(raw)
        responses = load_response_set(raw)
    return evaluate_suite(suite, responses, capabilities=caps)


def _status(results, task_id, check):
    task = next(t for t in results["tasks"] if t["task_id"] == task_id)
    return next(c["status"] for c in task["checks"] if c["check"] == check)


def _set_reply(raw, task_id, text, **extra):
    for row in raw["responses"]:
        if row["task_id"] == task_id:
            row["raw"] = text
            row.update(extra)


class CapabilityModeTests(unittest.TestCase):
    """四种模式：仅语言、单独时空、单独长上下文、两者联合。"""

    def test_language_only_runs_without_any_temporal_schema(self):
        res = _run("language-only", "language-only.healthy", "")
        self.assertEqual(res["gate"]["verdict"], "PASS")
        self.assertEqual(res["capabilities"], ["style"])
        self.assertTrue(all("时空证据上下文" not in m["content"] for t in res["tasks"] for m in t["messages"]))
        self.assertGreater(res["aggregate"]["axes"]["style"]["decided_checks"], 0)

    def test_capability_disabled_marks_grounding_not_applicable_and_keeps_style(self):
        res = _run("mygo-five-showcase", "mygo-five-showcase.healthy", "")
        self.assertEqual(res["gate"]["verdict"], "PASS")
        self.assertEqual(res["aggregate"]["axes"]["grounding"]["decided_checks"], 0)
        for task in res["tasks"]:
            self.assertFalse(task["applicable"])
            self.assertTrue(all("时空证据上下文" not in m["content"] for m in task["messages"]),
                            "能力未启用时证据块不得进 prompt")

    def test_spatiotemporal_enabled(self):
        self.assertEqual(_run("spatiotemporal-core", "spatiotemporal-core.healthy",
                              "spatiotemporal")["gate"]["verdict"], "PASS")
        self.assertEqual(_run("spatiotemporal-core", "spatiotemporal-core.defects",
                              "spatiotemporal")["gate"]["verdict"], "FAIL")

    def test_long_context_alone_and_joint(self):
        alone = _run("long-context-smoke", "builtin:long-context-smoke.healthy", "long-context-stress")
        joint = _run("long-context-smoke", "builtin:long-context-smoke.healthy",
                     "long-context-stress,spatiotemporal")
        self.assertEqual(alone["gate"]["verdict"], "PASS")
        self.assertEqual(joint["gate"]["verdict"], "PASS")
        conflict = [t for t in alone["tasks"] if t["family_id"] == "lcf-conflict-01"]
        self.assertTrue(conflict and all(not t["applicable"] for t in conflict),
                        "需要两项能力的任务只启用一项时必须 not_applicable")
        self.assertTrue(all(t["applicable"] for t in joint["tasks"] if t["family_id"] == "lcf-conflict-01"))

    def test_enabled_capability_with_no_applicable_sample_cannot_pass(self):
        res = _run("language-only", "language-only.healthy", "spatiotemporal")
        self.assertEqual(res["gate"]["verdict"], "FAIL")
        self.assertTrue(any("零样本" in r for r in res["gate"]["reasons"]))

    def test_all_not_applicable_cannot_pass(self):
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "")
        self.assertEqual(res["gate"]["verdict"], "FAIL")


class ResponseSemanticsTests(unittest.TestCase):
    def test_empty_is_not_abstention_and_error_is_not_pass(self):
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "spatiotemporal",
                   lambda r: (_set_reply(r, "st-unknown-01", ""),
                              _set_reply(r, "st-current-01", "", error="Timeout")))
        self.assertEqual(_status(res, "st-unknown-01", "response.abstain"), "empty")
        self.assertEqual(_status(res, "st-current-01", "response.required_claims"), "error")
        self.assertEqual(res["gate"]["verdict"], "FAIL")

    def test_dry_run_placeholders_never_pass(self):
        def dry(raw):
            raw["runner"] = {"kind": "dry-run", "synthetic": "dry_run"}
            for row in raw["responses"]:
                row["raw"], row["synthetic"] = "", "dry_run"
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "spatiotemporal", dry)
        self.assertEqual(res["gate"]["verdict"], "FAIL")
        self.assertEqual(res["aggregate"]["quality"]["dry_run"], 12)

    def test_unknown_is_not_negation(self):
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "spatiotemporal",
                   lambda r: _set_reply(r, "st-unknown-01", "北门没有人。"))
        self.assertEqual(_status(res, "st-unknown-01", "response.forbidden_claims"), "fail")

    def test_open_paraphrase_goes_to_needs_review_not_pass(self):
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "spatiotemporal",
                   lambda r: _set_reply(r, "st-current-01", "就在车站靠太阳升起那一边的门口。"))
        self.assertEqual(_status(res, "st-current-01", "response.required_claims"), "needs_review")
        self.assertEqual(res["gate"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(res["gate"]["exit_code"], 3)

    def test_human_label_resolves_needs_review_and_is_attributed(self):
        suite = load_suite("spatiotemporal-core")
        raw = copy.deepcopy(read_json_source("spatiotemporal-core.healthy"))
        _set_reply(raw, "st-current-01", "就在车站靠太阳升起那一边的门口。")
        labels = {"schema_version": "labels/v1", "labeler": "r1", "blind": True,
                  "labels": [{"task_id": "st-current-01", "check": "response.required_claims",
                              "status": "pass", "note": "改写，等价于东侧入口"}],
                  "judge": [{"task_id": "st-current-01", "judge_model": "m", "generator_model": "m",
                             "same_family": True, "verdict": "pass"}]}
        res = evaluate_suite(suite, load_response_set(raw), capabilities="spatiotemporal", labels=labels)
        task = next(t for t in res["tasks"] if t["task_id"] == "st-current-01")
        check = next(c for c in task["checks"] if c["check"] == "response.required_claims")
        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["label_source"], "human:r1:blind")
        self.assertEqual(task["auxiliary_judge"][0]["verdict"], "pass")   # judge 只记录，不改判定
        self.assertEqual(res["gate"]["verdict"], "PASS")

    def test_citation_only_applies_when_task_requires_it(self):
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "spatiotemporal")
        self.assertEqual(_status(res, "st-current-01", "response.citation"), "not_applicable")
        self.assertEqual(_status(res, "st-citation-01", "response.citation"), "pass")

    def test_budget_trim_separates_assembly_loss_from_model_behaviour(self):
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "spatiotemporal")
        task = next(t for t in res["tasks"] if t["task_id"] == "st-budget-01")
        self.assertIn("on_demand_evidence", task["trace"]["trimmed"])
        self.assertEqual(_status(res, "st-budget-01", "boundary.evidence_visible"), "pass")
        self.assertEqual(_status(res, "st-budget-01", "response.abstain"), "pass")

    def test_private_provenance_is_not_rendered(self):
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "spatiotemporal")
        task = next(t for t in res["tasks"] if t["task_id"] == "st-private-01")
        joined = "\n".join(m["content"] for m in task["messages"])
        self.assertNotIn("reviewer_note", joined)
        self.assertNotIn("复核人员备注", joined)
        self.assertEqual(_status(res, "st-private-01", "boundary.private_metadata_absent"), "pass")

    def test_every_check_carries_applicability_reason_and_denominator_fields(self):
        res = _run("spatiotemporal-core", "spatiotemporal-core.healthy", "spatiotemporal")
        for task in res["tasks"]:
            for check in task["checks"]:
                for key in ("applicability", "status", "reason", "numerator", "denominator", "stage",
                            "axis", "scorer_version"):
                    self.assertIn(key, check)
        rate = res["aggregate"]["axes"]["grounding"]["checks"]["response.citation"]
        self.assertEqual(rate["denominator"], 1, "not_applicable 不进分母")


class StyleAxisTests(unittest.TestCase):
    def test_wheel_only_install_marks_tool_scorers_unavailable_not_pass(self):
        from idiolect.evals import style_axis

        style_axis.load_tools.cache_clear()
        try:
            with mock.patch.dict(os.environ, {"IDIOLECT_STYLE_TOOLS": "0"}):
                res = _run("language-only", "language-only.healthy", "")
        finally:
            style_axis.load_tools.cache_clear()
        cov = res["aggregate"]["coverage"]
        self.assertIn("style.oob_high", cov["scorer_unavailable"])
        self.assertTrue(any("缺评分模块" in n for n in res["gate"]["notes"]))
        self.assertEqual(res["gate"]["verdict"], "PASS")   # length_cap 仍有有效判定

    def test_tools_present_but_dependency_missing_degrades_instead_of_crashing(self):
        import sys

        from idiolect.evals import style_axis

        style_axis.load_tools.cache_clear()
        try:
            # 模拟仓库 tools/ 在场、但 jieba 没装：分词首次导入 jieba 时失败
            with mock.patch.dict(sys.modules, {"jieba": None}):
                features = sys.modules.get("style_features")
                if features is not None:              # 清掉分词器缓存，迫使它重新导入 jieba
                    features._jieba = None
                self.assertIsNone(style_axis.load_tools())
                res = _run("language-only", "language-only.healthy", "")
        finally:
            style_axis.load_tools.cache_clear()
        self.assertEqual(res["gate"]["verdict"], "PASS")
        self.assertIn("style.sentence_cap", res["aggregate"]["coverage"]["scorer_unavailable"])

    def test_length_cap_uses_the_same_number_written_into_the_prompt(self):
        from idiolect.scene_classifier import classify
        from idiolect.style_target import build_style_target_block, style_caps

        caps = style_caps("乐奈", classify("我一直在哭，快撑不住了", "乐奈") or "")
        block = build_style_target_block("乐奈", caps["scene"])
        self.assertIn(f"总字数 ≤ **{caps['cap_chars']}**", block)
        res = _run("language-only", "language-only.healthy", "",
                   lambda r: _set_reply(r, "lang-rana-comfort", "嗯" * (caps["cap_chars"] + 1)))
        self.assertEqual(_status(res, "lang-rana-comfort", "style.length_cap"), "fail")


if __name__ == "__main__":
    unittest.main()
