"""dump 读取同一装配器、替换末条 user，并保持诊断无副作用。"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dump_consistency',ROOT/'tools/gates/dump_prompt.py')
dump=importlib.util.module_from_spec(spec)
spec.loader.exec_module(dump)


class DumpConsistencyTests(unittest.TestCase):
    def test_history_kept_and_current_user_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'fixtures').mkdir()
            fixture=[{'role':'system','content':'old'},{'role':'user','content':'prior user'},
                     {'role':'assistant','content':'prior reply'},{'role':'user','content':'placeholder'}]
            (root/'fixtures/messages_乐奈.json').write_text(json.dumps(fixture),encoding='utf8')
            with patch.object(dump,'ROOT',root),patch.object(dump,'REPORT',root/'out'):
                dump.write_dump('乐奈','one','你今天又想去哪找猫','current',dump.LAYERS,quiet=True)
                first=json.loads((root/'out/prompt_rana_current_one.json').read_text(encoding='utf8'))
                dump.write_dump('乐奈','one','你今天又想去哪找猫','current',dump.LAYERS,quiet=True)
                second=json.loads((root/'out/prompt_rana_current_one.json').read_text(encoding='utf8'))
            self.assertEqual(first,second)
            self.assertEqual(first[1:-1],fixture[1:-1])
            self.assertEqual(first[-1],{'role':'user','content':'你今天又想去哪找猫'})
            self.assertEqual(len(first),len(fixture))

    def test_current_phase_preserves_flags(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(dump,'REPORT',Path(temp)),patch.dict(os.environ,{'RANA_TURN_LOGIC_ENABLED':'0'}), \
                 patch.object(dump,'_enable_flags') as enable,patch.object(dump,'_disable_flags') as disable, \
                 patch.object(sys,'argv',['dump','--char','乐奈','--msg','在干嘛','--phase','current']):
                self.assertEqual(dump.main(),0)
                enable.assert_not_called()
                disable.assert_not_called()
                self.assertEqual(os.environ['RANA_TURN_LOGIC_ENABLED'],'0')
