"""CLI 分层视图必须等于一次完整装配，参数错误不得静默成功。"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PromptViewTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', '-m', 'idiolect', *args],
                              cwd=ROOT, capture_output=True, text=True, encoding='utf8')

    def test_layer_view_equals_full_prompt(self):
        for char in ('爱音', '灯', '立希', '素世', '乐奈'):
            with self.subTest(char=char):
                full = self.run_cli('prompt', char, '你今天又想去哪找猫')
                view = self.run_cli('prompt', char, '你今天又想去哪找猫',
                                    '--layers', 'canon,voice,style_target,turn_logic')
                self.assertEqual(full.returncode, 0)
                self.assertEqual(view.returncode, 0)
                body = re.sub(r'^── (?:canon|voice|style_target|turn_logic) ──\n', '',
                              view.stdout, flags=re.MULTILINE).strip()
                self.assertEqual(full.stdout.strip(), body)

    def test_disabled_dynamic_layer_is_not_printed(self):
        result = self.run_cli('prompt', '乐奈', '你今天又想去哪找猫',
                              '--no-turn-logic', '--layers', 'turn_logic')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_invalid_and_empty_layer_selections_fail(self):
        for selection in ('typo', 'canon,typo', ',', ' ', ''):
            with self.subTest(selection=selection):
                result = self.run_cli('prompt', '乐奈', '你好', '--layers', selection)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.strip())
