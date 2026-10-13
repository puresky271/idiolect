"""证据合同 v1 的行为契约：严格解析、可见/评估隔离、安全渲染与旧 API 兼容。

每条断言对应一个具体风险：缺字段被静默补成 current、悬空引用、不可见记录混进
可见包、私有路径或评估字段经 provenance 进入 messages、旧无版本写法被悄悄当成新
严格协议。全部离线、确定性。
"""
from __future__ import annotations

import copy
import unittest
import warnings

from idiolect.evidence_contract import (
    EVIDENCE_CONTEXT_SCHEMA,
    ContractError,
    EvidenceEnvelope,
    TemporalEvidenceContext,
    find_forbidden_values,
    parse_evidence_context,
    render_evidence_block,
    validate_evidence_context,
)


def _ctx(**over):
    base = {
        "schema_version": EVIDENCE_CONTEXT_SCHEMA,
        "observer_id": "actor_a",
        "as_of": "2026-09-12T15:00:00+09:00",
        "scene_id": "scene_02",
        "current": [{
            "evidence_id": "evidence_17", "status": "current",
            "text": "actor_b 在车站东侧入口。",
            "evidence_refs": ["synthetic://obs-017"],
            "provenance": {"source": "fixture", "modality": "text"},
        }],
        "history": [{
            "evidence_id": "evidence_09", "status": "history",
            "text": "周三排练时 actor_b 在旧练习室。",
            "as_of": "2026-09-09T18:30:00+09:00",
        }],
        "unknown": [],
    }
    base.update(over)
    return base


def _codes(report):
    return {issue.code for issue in report.issues if issue.severity == "error"}


class StrictParseTests(unittest.TestCase):
    def test_valid_context_parses_and_roundtrips(self):
        ctx = parse_evidence_context(_ctx())
        self.assertEqual([e.evidence_id for e in ctx.current], ["evidence_17"])
        again = parse_evidence_context(ctx.to_contract())
        self.assertEqual(again, ctx)

    def test_unknown_or_missing_schema_version_is_rejected(self):
        self.assertIn("schema_unknown", _codes(validate_evidence_context(_ctx(schema_version="evidence-context/v9"))))
        raw = _ctx()
        raw.pop("schema_version")
        self.assertIn("schema_missing", _codes(validate_evidence_context(raw)))

    def test_missing_status_is_not_defaulted_to_current(self):
        raw = _ctx()
        raw["current"][0].pop("status")
        report = validate_evidence_context(raw)
        self.assertFalse(report.ok)
        self.assertIn("missing_field", _codes(report))
        with self.assertRaises(ContractError):
            parse_evidence_context(raw)

    def test_bucket_mismatch_duplicate_and_dangling_refs(self):
        raw = _ctx()
        raw["current"].append(dict(raw["history"][0]))           # history 记录塞进 current 桶
        self.assertIn("status_bucket_mismatch", _codes(validate_evidence_context(raw)))
        raw = _ctx()
        raw["history"][0]["evidence_id"] = "evidence_17"           # 重复 ID
        self.assertIn("duplicate_id", _codes(validate_evidence_context(raw)))
        raw = _ctx()
        raw["current"][0]["supersedes"] = ["evidence_404"]         # 悬空引用
        self.assertIn("dangling_ref", _codes(validate_evidence_context(raw)))

    def test_type_errors_and_unknown_fields(self):
        raw = _ctx()
        raw["current"][0]["evidence_refs"] = "synthetic://x"       # 应为列表
        self.assertIn("type_error", _codes(validate_evidence_context(raw)))
        raw = _ctx()
        raw["current"][0]["stauts"] = "current"                    # 拼写错误不能被吞掉
        self.assertIn("unknown_field", _codes(validate_evidence_context(raw)))

    def test_time_rules(self):
        raw = _ctx()
        raw["history"][0]["as_of"] = "2026-09-20T00:00:00+09:00"  # 晚于本轮 as_of
        self.assertIn("future_evidence", _codes(validate_evidence_context(raw)))
        raw = _ctx()
        raw["current"][0]["valid_until"] = "2026-09-10T00:00:00+09:00"  # 已过期却标 current
        self.assertIn("expired_current", _codes(validate_evidence_context(raw)))
        raw = _ctx()
        raw["history"][0]["as_of"] = "2026-09-09 18:30"            # 无时区
        self.assertIn("bad_time", _codes(validate_evidence_context(raw)))

    def test_visibility_and_private_metadata(self):
        raw = _ctx()
        raw["current"][0]["visible_to"] = ["actor_b"]              # 对方可见、观察者不可见
        self.assertIn("visibility_violation", _codes(validate_evidence_context(raw)))
        raw = _ctx()
        raw["current"][0]["evidence_refs"] = ["D:/private/ledger.sqlite"]
        self.assertIn("private_locator", _codes(validate_evidence_context(raw)))
        raw = _ctx()
        raw["current"][0]["provenance"] = {"gold_answer": "东侧入口"}
        self.assertIn("forbidden_provenance_key", _codes(validate_evidence_context(raw)))
        raw = _ctx()
        raw["current"][0]["provenance"] = {"note": "C:\\Users\\someone\\chat.db"}
        self.assertIn("private_value", _codes(validate_evidence_context(raw)))


class RenderTests(unittest.TestCase):
    def test_render_only_allowlisted_provenance(self):
        raw = _ctx()
        raw["current"][0]["provenance"] = {"source": "fixture", "modality": "text", "reviewer": "x"}
        block = render_evidence_block(parse_evidence_context(raw))
        self.assertIn("source=fixture", block)
        self.assertNotIn("reviewer", block)

    def test_permissions_can_extend_render_allowlist_but_not_forbidden_keys(self):
        raw = _ctx(permissions={"declared_by": "fixture", "render_provenance_keys": ["reviewer"]})
        raw["current"][0]["provenance"] = {"reviewer": "r1"}
        block = render_evidence_block(parse_evidence_context(raw))
        self.assertIn("reviewer=r1", block)

    def test_render_marks_buckets_and_history_time(self):
        block = render_evidence_block(parse_evidence_context(_ctx()))
        self.assertIn("[当前证据]", block)
        self.assertIn("[历史证据]", block)
        self.assertIn("[未知边界]", block)
        self.assertIn("2026-09-09T18:30:00+09:00", block)      # 历史条目带时间，便于限定
        self.assertNotIn("observer_id", block)                  # 元数据不进可见文本

    def test_find_forbidden_values_normalizes_representation(self):
        messages = [{"role": "system", "content": "库存 １，２００ 件"}]
        self.assertEqual(find_forbidden_values(messages, ["1200"]), ["1200"])
        self.assertEqual(find_forbidden_values(messages, ["1300"]), [])


class LegacyCompatTests(unittest.TestCase):
    def test_legacy_unversioned_dict_still_loads_with_deprecation(self):
        legacy = {"as_of": None, "current": [{"text": "旧写法", "evidence_id": "e1"}]}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ctx = TemporalEvidenceContext.from_dict(legacy)
        self.assertEqual(ctx.current[0].status, "current")
        self.assertTrue(any(issubclass(w.category, DeprecationWarning) for w in caught))

    def test_versioned_dict_through_legacy_entry_is_strict(self):
        raw = _ctx()
        raw["current"][0].pop("status")
        with self.assertRaises(ContractError):
            TemporalEvidenceContext.from_dict(raw)

    def test_workspace_reexports_same_classes(self):
        from idiolect import workspace

        self.assertIs(workspace.EvidenceEnvelope, EvidenceEnvelope)
        self.assertIs(workspace.TemporalEvidenceContext, TemporalEvidenceContext)
        self.assertIs(workspace.KnowledgeProjection, TemporalEvidenceContext)

    def test_parse_does_not_mutate_input(self):
        raw = _ctx()
        snapshot = copy.deepcopy(raw)
        parse_evidence_context(raw)
        self.assertEqual(raw, snapshot)


if __name__ == "__main__":
    unittest.main()
