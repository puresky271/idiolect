"""实验 manifest 与可比性契约：缺字段 → incomparable；非干预变化 → blocked；产物被改 → fail closed。"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from idiolect.evals.manifest import (
    ExperimentRegistry,
    StaleArtifactError,
    build_manifest,
    compare_manifests,
    compare_results,
)
from idiolect.evals.pipeline import evaluate_suite
from idiolect.evals.suites import load_responses, load_suite, read_json_source, suite_source


def _results(replay="spatiotemporal-core.healthy"):
    suite = load_suite("spatiotemporal-core")
    res = evaluate_suite(suite, load_responses(f"builtin:{replay}", suite), capabilities="spatiotemporal")
    return res, read_json_source(replay)


def _manifest(intervention=None, replay="spatiotemporal-core.healthy"):
    res, raw = _results(replay)
    return build_manifest(res, suite_raw=suite_source("spatiotemporal-core"), responses_raw=raw,
                          intervention=intervention or []), res


class ManifestTests(unittest.TestCase):
    def test_manifest_records_versions_without_secrets(self):
        manifest, _ = _manifest()
        blob = json.dumps(manifest, ensure_ascii=False)
        for key in ("api_key", "LLM_API_KEY", "base_url"):
            self.assertNotIn(f'"{key}"', blob)
        self.assertEqual(manifest["redaction"]["secrets_stored"], False)
        for path in ("code", "suite", "generation", "scorers", "prompt", "clock", "capabilities"):
            self.assertIn(path, manifest)
        self.assertIn("dirty", manifest["code"])

    def test_identical_runs_are_comparable(self):
        a, _ = _manifest()
        b, _ = _manifest()
        self.assertEqual(compare_manifests(a, b)["status"], "comparable")

    def test_undeclared_change_blocks_pooling_and_improvement(self):
        a, _ = _manifest()
        for path, value in (("generation.model", "other"), ("clock.now", "2026-09-12T03:00:00+09:00"),
                            ("scorers.source_sha256", "x"), ("labels.sha256", "y"), ("suite.sha256", "z")):
            b = copy.deepcopy(a)
            node = b
            *parents, leaf = path.split(".")
            for p in parents:
                node = node[p]
            node[leaf] = value
            verdict = compare_manifests(a, b)
            self.assertEqual(verdict["status"], "blocked", path)
            self.assertFalse(verdict["pooling_allowed"])
            self.assertFalse(verdict["improvement_claim_allowed"])

    def test_preregistered_intervention_is_allowed(self):
        a, _ = _manifest(intervention=["prompt"])
        b = copy.deepcopy(a)
        b["prompt"]["messages_sha256"] = "changed"
        b["code"]["package_source_sha256"] = "changed"
        self.assertEqual(compare_manifests(a, b)["status"], "comparable")

    def test_intervention_declarations_must_match(self):
        a, _ = _manifest(intervention=["prompt"])
        b, _ = _manifest(intervention=["model"])
        self.assertEqual(compare_manifests(a, b)["status"], "blocked")

    def test_missing_field_is_incomparable_not_assumed_equal(self):
        a, _ = _manifest()
        b = copy.deepcopy(a)
        del b["clock"]["now"]
        self.assertEqual(compare_manifests(a, b)["status"], "incomparable")

    def test_legacy_batch_without_manifest_is_incomparable(self):
        a, _ = _manifest()
        verdict = compare_manifests(a, {"label": "repo_standalone", "summary": {}})
        self.assertEqual(verdict["status"], "incomparable")

    def test_dry_run_side_is_blocked(self):
        a, _ = _manifest()
        b = copy.deepcopy(a)
        b["generation"]["synthetic"] = "dry_run"
        self.assertEqual(compare_manifests(a, b)["status"], "blocked")

    def test_compare_results_refuses_judgement_when_blocked(self):
        a, ra = _manifest()
        b, rb = _manifest(replay="spatiotemporal-core.defects")
        ok = compare_manifests(a, b)
        self.assertEqual(compare_results(ra, rb, ok)["axes"]["grounding"]["judgement"], "regressed")
        blocked = dict(ok, improvement_claim_allowed=False, status="blocked")
        self.assertEqual(compare_results(ra, rb, blocked)["axes"]["grounding"]["judgement"], "refused")


class RegistryTests(unittest.TestCase):
    def test_tampered_artifact_fails_closed(self):
        res, raw = _results()
        manifest = build_manifest(res, suite_raw=suite_source("spatiotemporal-core"), responses_raw=raw)
        with tempfile.TemporaryDirectory() as tmp:
            reg = ExperimentRegistry(Path(tmp))
            folder = reg.save(res, manifest, raw)
            results, _ = reg.load(folder)
            self.assertEqual(results["gate"]["verdict"], "PASS")
            path = folder / "results.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["gate"]["verdict"] = "PASS!"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(StaleArtifactError):
                reg.load(folder)
            index = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index[0]["verdict"], "PASS")

    def test_folder_without_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(StaleArtifactError):
                ExperimentRegistry.load(Path(tmp))


if __name__ == "__main__":
    unittest.main()
