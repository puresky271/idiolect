"""显式快照 adapter 契约：只消费声明过脱敏与权限的快照，不推导时态，不放行不可见记录。"""
from __future__ import annotations

import copy
import unittest

from idiolect.adapters import ExplicitSnapshotAdapter, get_adapter
from idiolect.evals.suites import read_json_source


def _snap():
    return copy.deepcopy(read_json_source("builtin:snapshot.example"))


def _codes(result):
    return {i.code for i in result.report.issues if i.severity == "error"}


class SnapshotAdapterTests(unittest.TestCase):
    def test_example_projects_and_drops_invisible_records_without_text(self):
        result = ExplicitSnapshotAdapter().to_context(_snap())
        self.assertTrue(result.ok)
        self.assertEqual({d["record_id"] for d in result.dropped}, {"evidence_33", "evidence_55"})
        self.assertNotIn("text", str(result.dropped))          # 丢弃记录只留 ID 与原因
        rendered = result.context.render()
        self.assertNotIn("私聊", rendered)
        self.assertIn("evidence_17", rendered)

    def test_unredacted_or_unpermissioned_snapshot_is_refused(self):
        snap = _snap()
        snap["redaction"]["applied"] = False
        self.assertIn("not_redacted", _codes(ExplicitSnapshotAdapter().to_context(snap)))
        snap = _snap()
        del snap["permissions"]["observer_id"]
        self.assertIn("permissions_missing", _codes(ExplicitSnapshotAdapter().to_context(snap)))

    def test_evaluator_or_production_payload_is_refused(self):
        snap = _snap()
        snap["oracle"] = {"truth": "x"}
        self.assertIn("evaluator_or_production_payload", _codes(ExplicitSnapshotAdapter().to_context(snap)))

    def test_status_is_never_inferred_from_timestamps(self):
        snap = _snap()
        snap["records"][0].pop("status")
        result = ExplicitSnapshotAdapter().to_context(snap)
        self.assertFalse(result.ok)
        self.assertIn("status_not_projected", _codes(result))

    def test_private_locator_is_rejected(self):
        snap = _snap()
        snap["records"][0]["locator"] = "C:\\Users\\someone\\memory.sqlite"
        self.assertIn("private_locator", _codes(ExplicitSnapshotAdapter().to_context(snap)))

    def test_adapter_lookup(self):
        self.assertEqual(get_adapter("explicit-snapshot").name, "explicit-snapshot")
        with self.assertRaises(ValueError):
            get_adapter("auto-open-production-db")


if __name__ == "__main__":
    unittest.main()
