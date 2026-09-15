"""离线报告不得把模型输出当作 HTML，也不得把缺测补成零分。"""
import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('report_html',ROOT/'tools/score/report_html.py')
report=importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportHtmlTests(unittest.TestCase):
    def test_repetition_requires_matching_source_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            raw=json.dumps(dict(char='灯',scenario='a',reply='你好')).encode('utf8')
            (path/'probe_run.jsonl').write_bytes(raw)
            repeat_path=path/'repeat_run.json'
            repeat_path.write_text(json.dumps({'source_sha256':'wrong','cells':[]}),encoding='utf8')
            self.assertEqual(report.load_batch(path,'run')['repetition_status'],'stale')
            repeat_path.write_text(json.dumps({'source_sha256':hashlib.sha256(raw).hexdigest(),'cells':[]}),encoding='utf8')
            self.assertEqual(report.load_batch(path,'run')['repetition_status'],'available')

    def test_comparison_never_treats_missing_fields_as_equal(self):
        old={'summary':{}}
        self.assertTrue(all(r['status']=='unknown' for r in report.compare_conditions(old,old)))
        a={'summary':{'metadata':{'model':'one','temperature':0,'dry_run':False}}}
        b={'summary':{'metadata':{'model':'two','temperature':0,'dry_run':False}}}
        rows={r['field']:r for r in report.compare_conditions(a,b)}
        self.assertEqual(rows['model']['status'],'different')
        self.assertEqual(rows['temperature']['status'],'same')
        self.assertEqual(rows['dry_run']['status'],'same')
        self.assertEqual(rows['fixture_sha256']['status'],'unknown')

    def test_legacy_batch_and_script_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            row=dict(char='灯',scenario='comfort',reply='</script><script>alert(1)</script>')
            (path/'probe_old.jsonl').write_text(json.dumps(row),encoding='utf8')
            batch=report.load_batch(path,'old')
            self.assertEqual(batch['summary'],{})
            self.assertEqual(batch['scores'],[])
            html=report.render([batch])
            self.assertNotIn(row['reply'],html)
            payload=html.split('id="data">',1)[1].split('</script>',1)[0]
            self.assertEqual(json.loads(payload)[0]['rows'][0]['reply'],row['reply'])

    def test_invalid_input_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            with self.assertRaises(ValueError):
                report.load_batch(path,'../escape')
            (path/'probe_bad.jsonl').write_text('{"reply":null}',encoding='utf8')
            with self.assertRaises(ValueError):
                report.load_batch(path,'bad')
        with self.assertRaises(ValueError):
            report.render([])
