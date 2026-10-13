"""长上下文压力能力契约：确定性生成、只动声明过的因子、计量诚实、family 是独立单位。"""
from __future__ import annotations

import copy
import unittest

from idiolect.evals.longctx import generate_suite, measure, paired_families, synthetic_replay
from idiolect.evals.pipeline import evaluate_suite, load_response_set
from idiolect.evals.suites import load_suite, read_json_source
from idiolect.evals.tasks import canonical_sha256, parse_suite


def _plan():
    return copy.deepcopy(read_json_source("builtin:long-context-smoke"))


class GeneratorTests(unittest.TestCase):
    def test_generation_is_deterministic(self):
        self.assertEqual(canonical_sha256(generate_suite(_plan())), canonical_sha256(generate_suite(_plan())))

    def test_matrix_shape_and_declared_interventions(self):
        suite = parse_suite(generate_suite(_plan()))
        lenpos = [t for t in suite.tasks if t.family_id == "lcf-lenpos-01"]
        self.assertEqual(len(lenpos), 6)                                 # 2 长度 × 3 位置
        self.assertEqual(sum(t.long_context["is_control"] for t in lenpos), 1)
        for t in lenpos:
            self.assertEqual(set(t.long_context["factors"]), set(t.long_context["intervention"]))
            self.assertEqual(t.user, lenpos[0].user)                      # 语义任务固定
            self.assertEqual(t.raw["expect"], lenpos[0].raw["expect"])    # 期望标签固定

    def test_distractors_never_contain_expected_claims(self):
        suite = generate_suite(_plan())
        for task in suite["tasks"]:
            words = [w for c in task["expect"].get("required_claims", []) for w in c["any_of"]]
            key_ids = {c.get("evidence_id") for c in task["expect"].get("required_claims", [])}
            for bucket in ("current", "history", "unknown"):
                for item in task["evidence_context"][bucket]:
                    if item["evidence_id"] in key_ids:
                        continue
                    for w in words:
                        self.assertNotIn(w, item["text"], task["task_id"])

    def test_long_arm_is_longer_and_position_moves_only_the_key(self):
        res = _eval("long-context-smoke.healthy")
        rows = {t["arm"]: measure(t) for t in res["tasks"] if t["family_id"] == "lcf-lenpos-01"}
        self.assertGreater(rows["length=long,position=head"]["total_chars"],
                           3 * rows["length=short,position=head"]["total_chars"])
        self.assertEqual(rows["length=long,position=head"]["key_position_index"], 0)
        self.assertEqual(rows["length=long,position=tail"]["key_position_fraction"], 1.0)
        mid = rows["length=long,position=middle"]["key_position_fraction"]
        self.assertTrue(0.3 < mid < 0.7)
        self.assertEqual(rows["length=long,position=head"]["tokens"], None)
        self.assertEqual(rows["length=long,position=head"]["tokenizer"], "unknown")

    def test_optional_tokenizer_is_recorded(self):
        res = _eval("long-context-smoke.healthy")
        row = measure(res["tasks"][0], tokenizer=lambda s: len(s) // 2, tokenizer_name="halves@1")
        self.assertEqual(row["tokenizer"], "halves@1")
        self.assertIsInstance(row["tokens"], int)


def _eval(policy, caps="long-context-stress,spatiotemporal"):
    suite = load_suite("long-context-smoke")
    responses = load_response_set(synthetic_replay(suite.raw, policy.split(".", 1)[1]))
    return evaluate_suite(suite, responses, capabilities=caps)


class PairedAnalysisTests(unittest.TestCase):
    def test_healthy_replay_passes_with_underpowered_note(self):
        res = _eval("long-context-smoke.healthy")
        self.assertEqual(res["gate"]["verdict"], "PASS")
        self.assertTrue(any("结论强度不足" in n for n in res["gate"]["notes"]))

    def test_lost_middle_is_isolated_to_long_middle_arms(self):
        res = _eval("long-context-smoke.lost_middle")
        failing = {t["arm"] for t in res["tasks"] if t["summary"]["grounding"] == "fail"}
        self.assertEqual(failing, {"length=long,position=middle"})
        paired = paired_families(res)
        self.assertEqual(paired["by_factor_level"]["position=middle"]["degraded"], 2)
        self.assertEqual(paired["family_sign_test"]["regressed"], 2)
        self.assertFalse(paired["family_sign_test"]["conclusive"], "2 个 family 不能下结论")

    def test_budget_control_is_attributed_to_assembly_not_model(self):
        res = _eval("long-context-smoke.healthy")
        trimmed = next(t for t in res["tasks"] if t["arm"] == "budget=trimmed")
        self.assertIn("on_demand_evidence", trimmed["trace"]["trimmed"])
        self.assertFalse(measure(trimmed)["key_evidence_present"])
        self.assertEqual(trimmed["summary"]["grounding"], "pass")

    def test_failure_controls_cannot_pass(self):
        res = _eval("long-context-smoke.failure_controls")
        self.assertEqual(res["gate"]["verdict"], "FAIL")
        q = res["aggregate"]["quality"]
        self.assertGreater(q["empty"], 0)
        self.assertGreater(q["error"], 0)

    def test_multiturn_trace_records_cumulative_history(self):
        res = _eval("long-context-smoke.healthy")
        rows = {t["arm"]: t for t in res["tasks"] if t["family_id"] == "lcf-conflict-01"}
        short = rows["conflict=history_vs_current,turns=short"]["trace"]["history_messages"]
        long = rows["conflict=history_vs_current,turns=long"]["trace"]["history_messages"]
        self.assertEqual((short, long), (4, 48))


if __name__ == "__main__":
    unittest.main()
