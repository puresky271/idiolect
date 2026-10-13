"""同链变异自测契约：变异体必须经过真实链路被抓到；等价体不得被判差异；反控制不得误报。

另外钉住论文 Part I 的两条教训：吞掉隐藏参数的空洞门禁必须被金丝雀抓到；认证范围内的
表示算子必须保持判决。
"""
from __future__ import annotations

import unittest

from idiolect.evals import mutants
from idiolect.evals.matching import certify_operators
from idiolect.evals.pipeline import Components, validity_probes


class SelfTestContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = mutants.run_selftest()

    def test_baseline_passes_and_no_survivors_or_false_positives(self):
        s = self.report["summary"]
        self.assertEqual(self.report["baseline"]["exit_code"], 0)
        self.assertEqual(s["survivors"], [])
        self.assertEqual(s["control_false_positives"], [])
        self.assertTrue(s["ok"])

    def test_required_mutant_classes_present(self):
        descriptions = " ".join(m.description for m in mutants.MUTANTS)
        for needle in ("历史", "不可见", "伪造", "互换", "悬空", "前提", "未知被肯定", "未知被否定", "provenance",
                       "丢弃", "预算", "空回复", "applicability", "混批", "评分器", "wrapper", "空洞门禁", "干跑"):
            self.assertIn(needle, descriptions)

    def test_each_mutant_is_attributed_to_a_stage(self):
        for row in self.report["mutants"]:
            if row["expect"] == "killed":
                self.assertTrue(row["detected_by"], row["mutant_id"])
            else:
                self.assertEqual(row["outcome"], "equivalent")

    def test_detection_spans_multiple_stages(self):
        by_stage = self.report["summary"]["detected_by_stage"]
        for stage in ("structural", "prompt_boundary", "response", "aggregate", "compare"):
            self.assertGreater(by_stage[stage], 0, stage)

    def test_mutants_go_through_the_real_pipeline(self):
        scn = mutants.baseline()
        self.assertIsInstance(scn["components"], Components)
        out = mutants.run_scenario(mutants.MUTANTS[1].apply(mutants.baseline()))
        self.assertIsNotNone(out["results"])
        self.assertTrue(out["results"]["tasks"][0]["messages"], "必须装配出真实 messages")


class GateAdequacyTests(unittest.TestCase):
    def test_real_checkers_flip_on_canaries(self):
        self.assertTrue(all(row["flipped"] for row in validity_probes(Components())))

    def test_discarding_gate_is_caught_by_canary(self):
        comps = Components()
        real = comps.boundary
        comps.boundary = lambda task, ctx, msgs, trace, hidden: real(task, ctx, msgs, trace, [])
        rows = validity_probes(comps)
        self.assertFalse(next(r for r in rows if r["probe"] == "boundary.hidden_value_canary")["flipped"])

    def test_certified_operators_preserve_decisions(self):
        rows = certify_operators()
        self.assertTrue(all(r["preserved"] for r in rows if r["claimed"]))
        self.assertTrue(any(not r["claimed"] for r in rows), "必须列出未认证算子作为已知边界")


if __name__ == "__main__":
    unittest.main()
