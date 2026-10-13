"""统一 CLI 契约：退出码、零写（只写报告目录）、付费 runner 的显式 opt-in、inspect 报告转义。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from idiolect.__main__ import main
from idiolect.evals.report import render_inspect_html, safe_json_for_script
from idiolect.evals.suites import BUILTIN_REPLAYS, BUILTIN_SUITES, load_suite, read_json_source


def _cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(list(argv))
    return code, out.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"IDIOLECT_REPORT_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_eval_exit_codes_follow_gate(self):
        code, out = _cli("eval", "--suite", "spatiotemporal-core", "--responses",
                         "builtin:spatiotemporal-core.healthy", "--capabilities", "spatiotemporal")
        self.assertEqual(code, 0, out)
        code, _ = _cli("eval", "--suite", "spatiotemporal-core", "--responses",
                       "builtin:spatiotemporal-core.defects", "--capabilities", "spatiotemporal")
        self.assertEqual(code, 1)
        code, _ = _cli("eval", "--suite", "spatiotemporal-core", "--responses",
                       "builtin:spatiotemporal-core.defects", "--capabilities", "spatiotemporal", "--diagnostic")
        self.assertEqual(code, 0)

    def test_eval_writes_only_under_report_dir_and_compare_reads_back(self):
        _cli("eval", "--suite", "spatiotemporal-core", "--responses", "builtin:spatiotemporal-core.healthy",
             "--capabilities", "spatiotemporal", "--html")
        _cli("eval", "--suite", "spatiotemporal-core", "--responses", "builtin:spatiotemporal-core.defects",
             "--capabilities", "spatiotemporal")
        root = Path(self.tmp.name) / "experiments"
        folders = sorted(p for p in root.iterdir() if p.is_dir())
        self.assertEqual(len(folders), 2)
        self.assertTrue((folders[1] / "inspect.html").exists() or (folders[0] / "inspect.html").exists())
        code, out = _cli("compare", str(folders[1]), str(folders[0]))
        self.assertEqual(code, 0, out)
        self.assertIn("comparable", out)

    def test_paid_run_requires_yes_and_call_cap(self):
        code, _ = _cli("run", "--suite", "spatiotemporal-core")
        self.assertEqual(code, 2)
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "", "LLM_BASE_URL": "", "LLM_MODEL": ""}):
            code, _ = _cli("run", "--suite", "spatiotemporal-core", "--yes")
        self.assertEqual(code, 2)                      # 没有 --max-calls 上限 → 拒绝

    def test_dry_run_responses_fail_formal_eval(self):
        out_file = Path(self.tmp.name) / "dry.json"
        code, _ = _cli("run", "--suite", "spatiotemporal-core", "--capabilities", "spatiotemporal",
                       "--dry-run", "--out", str(out_file))
        self.assertEqual(code, 0)
        code, _ = _cli("eval", "--suite", "spatiotemporal-core", "--responses", str(out_file),
                       "--capabilities", "spatiotemporal", "--no-save")
        self.assertEqual(code, 1)

    def test_contract_validate_and_selftest(self):
        self.assertEqual(_cli("contract", "validate", "builtin:snapshot.example")[0], 0)
        self.assertEqual(_cli("selftest")[0], 0)
        self.assertEqual(_cli("capabilities")[0], 0)
        self.assertEqual(_cli("bench", "list")[0], 0)

    def test_legacy_commands_unchanged(self):
        code, out = _cli("sizes", "乐奈", "你今天又想去哪找猫")
        self.assertEqual(code, 0)
        self.assertIn("canon", out)


class PaidRunnerWithFakeClientTests(unittest.TestCase):
    def test_runner_binds_messages_and_records_errors(self):
        from idiolect.evals.runners import plan_requests, run_openai_compatible

        class _Choice:
            def __init__(self, text):
                self.message = type("M", (), {"content": text})()
                self.finish_reason = "stop"

        class _Fake:
            def __init__(self):
                self.chat = self
                self.completions = self
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                if self.calls == 2:
                    raise TimeoutError("synthetic")
                return type("R", (), {"choices": [_Choice("东侧入口。")]})()

        suite = load_suite("spatiotemporal-core")
        reqs = plan_requests(suite, capabilities="spatiotemporal")
        with self.assertRaises(PermissionError):
            run_openai_compatible(suite, reqs, allow_paid=False, max_calls=99, model="m",
                                  temperature=0.7, max_tokens=10, arm="x", client=_Fake())
        data = run_openai_compatible(suite, reqs, allow_paid=True, max_calls=99, model="m",
                                     temperature=0.7, max_tokens=10, arm="x", client=_Fake())
        self.assertTrue(all(r["messages_sha256"] for r in data["responses"]))
        self.assertTrue(data["responses"][1]["error"].startswith("TimeoutError"))
        self.assertNotIn("api_key", json.dumps(data))


class ReportEscapingTests(unittest.TestCase):
    def test_script_injection_is_escaped(self):
        hostile = "</script><script>alert(1)</script> "
        blob = safe_json_for_script({"x": hostile})
        self.assertNotIn("</script>", blob)
        self.assertNotIn(" ", blob)
        html = render_inspect_html([], selftest={"summary": {}, "mutants": [{"description": hostile}]})
        self.assertEqual(html.count("</script>"), 2)    # 只有模板自己的两个闭合标签


class PackageDataTests(unittest.TestCase):
    def test_shipped_replays_are_bound_to_current_suites(self):
        from idiolect.evals.tasks import canonical_sha256

        for name, filename in BUILTIN_REPLAYS.items():
            if filename is None:
                continue
            suite_name = name.split(".", 1)[0]
            raw = read_json_source(name)
            self.assertEqual(raw["suite_sha256"], load_suite(suite_name).sha256,
                             f"{name} 登记的 suite 指纹已过期：先确认回放仍对应修改后的任务，再重录")
            self.assertEqual(raw["runner"]["synthetic"], "replay")
            self.assertTrue(canonical_sha256(raw))

    def test_builtin_suites_validate(self):
        for name in BUILTIN_SUITES:
            self.assertTrue(load_suite(name).tasks)


if __name__ == "__main__":
    unittest.main()
