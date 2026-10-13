"""时空证据上下文契约：纯离线、可重复，不调用模型或外部服务。"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from idiolect.workspace import (
    EvidenceEnvelope,
    KnowledgeProjection,
    TemporalEvidenceContext,
    build_workspace_messages,
)


ROOT = Path(__file__).resolve().parents[1]


class TemporalEvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(
            (ROOT / "fixtures" / "temporal_evidence_cases.json").read_text(encoding="utf-8")
        )

    def _context(self, case):
        return TemporalEvidenceContext.from_dict(case["context"])

    def test_fixture_covers_current_history_unknown(self):
        statuses = {case["expected"]["status"] for case in self.fixture["cases"]}
        self.assertEqual(statuses, {"current", "history", "unknown"})

    def test_json_roundtrip_preserves_refs_and_provenance(self):
        for case in self.fixture["cases"]:
            with self.subTest(case=case["id"]):
                context = self._context(case)
                restored = TemporalEvidenceContext.from_dict(context.to_dict())
                self.assertEqual(restored, context)
                self.assertEqual(tuple(case["expected"]["refs"]), context.evidence_refs)
                rendered = context.render()
                for needle in case["expected"]["must_include"]:
                    self.assertIn(needle, rendered)

    def test_status_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            TemporalEvidenceContext(current=(EvidenceEnvelope("旧记录", status="history"),))

    def test_unknown_boundary_is_explicit_for_incorrect_premise(self):
        case = next(item for item in self.fixture["cases"] if item["id"] == "unknown-premise")
        context = self._context(case)
        rendered = context.render(include_provenance=False)
        self.assertIn("[未知边界]", rendered)
        self.assertIn("没有收到北门照片", rendered)
        self.assertNotIn("北门照片已确认", rendered)

    def test_workspace_integration_is_stable_and_keeps_evidence_refs(self):
        case = self.fixture["cases"][0]
        context = self._context(case)
        kwargs = {
            "include_turn_logic": False,
            "evidence_context": context,
            "blocks": [("current_state", "合成场景")],
        }
        first = build_workspace_messages("乐奈", case["user"], **kwargs)
        second = build_workspace_messages("乐奈", case["user"], **kwargs)
        self.assertEqual(first, second)
        evidence = next(message for message in first if "时空证据上下文" in message["content"])
        self.assertIn("synthetic://obs-001", evidence["content"])
        self.assertIn("车站东侧入口", evidence["content"])

    def test_mapping_input_and_alias_are_supported(self):
        case = self.fixture["cases"][1]
        context = self._context(case)
        self.assertIs(KnowledgeProjection, TemporalEvidenceContext)
        messages = build_workspace_messages(
            "乐奈", case["user"], include_turn_logic=False,
            evidence_context=context.to_dict(), include_evidence_provenance=False,
        )
        evidence = next(message for message in messages if "时空证据上下文" in message["content"])
        self.assertIn("[历史证据]", evidence["content"])
        self.assertNotIn("provenance:", evidence["content"])


if __name__ == "__main__":
    unittest.main()
