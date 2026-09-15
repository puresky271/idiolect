"""在模型调用边界捕获请求，离线验证四层装配不会被再次追加。"""
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def capture_requests():
    spec = importlib.util.spec_from_file_location('probe_request_test', ROOT / 'tools/probe/probe_runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    from idiolect.assemble import build_system_prompt
    cases = ('在干嘛', '我一直在哭，快撑不住了', '你今天又想去哪找猫', '明天几点上课')
    plan = {char: [dict(id=f'case_{i}',cat='audit',text=text) for i,text in enumerate(cases)]
            for char in runner.CHARS}
    expected = [build_system_prompt(char,text,session_id=f'expected:{char}:{i}',now=runner.MOCK.mock_now())
                for char in runner.CHARS for i,text in enumerate(cases)]
    calls=[]
    def create(**kwargs):
        calls.append(kwargs['messages'])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=''))])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    (ROOT/'report').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'report') as temp:
        with patch.object(runner,'REPORT',Path(temp)), patch.object(runner,'CORPUS_DIR',Path(temp)/'absent'), \
             patch.object(runner,'SCENARIOS',plan), patch.object(runner,'make_client',return_value=client), \
             patch.object(runner,'load_fixture',return_value=[{'role':'system','content':''},{'role':'user','content':'占位'}]), \
             patch.object(sys,'argv',['probe_runner','--label','request_gate','--assemble','--turn-logic','--runs','1']), \
             contextlib.redirect_stdout(io.StringIO()):
            rc=runner.main()
        records=[json.loads(line) for line in (Path(temp)/'probe_request_gate.jsonl').read_text(encoding='utf8').splitlines()]
        summary=json.loads((Path(temp)/'probe_request_gate_summary.json').read_text(encoding='utf8'))
    return dict(rc=rc,expected=expected,calls=calls,records=records,summary=summary)


class ProbeRequestTests(unittest.TestCase):
    def test_assembled_requests_match_single_assembly(self):
        result=capture_requests()
        self.assertEqual(result['rc'],0)
        self.assertEqual(len(result['calls']),20)
        for expected,call in zip(result['expected'],result['calls']):
            with self.subTest(user=call[-1]['content']):
                self.assertEqual(call[0]['content'],expected)
                self.assertEqual([m['role'] for m in call],['system','user'])
        metadata=result['summary']['metadata']
        self.assertEqual(metadata['schema_version'],1)
        self.assertEqual(metadata['temperature'],0.75)
        self.assertEqual(metadata['counts']['empty_content'],20)
        self.assertEqual(metadata['counts']['successful'],0)
        self.assertTrue(metadata['clock']['mocked'])
        self.assertEqual(len(metadata['fixture_sha256']),5)
        for row,call in zip(result['records'],result['calls']):
            encoded=json.dumps(call,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
            self.assertEqual(row['messages_sha256'],hashlib.sha256(encoded).hexdigest())
            self.assertEqual(row['user_text'],call[-1]['content'])
