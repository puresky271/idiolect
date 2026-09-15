"""重复率只统计有效输出；错误、空白、零样本分别报告。"""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('repeat_rate',ROOT/'tools/score/_repeat_rate.py')
repeat=importlib.util.module_from_spec(spec)
spec.loader.exec_module(repeat)


class RepetitionTests(unittest.TestCase):
    def test_errors_and_empty_are_excluded_without_losing_counts(self):
        rows=[dict(char='灯',scenario='a',cat='x',reply=text,error=error)
              for text,error in [('你好',''),('你好',''),('不同',''),('',''),('无效','timeout')]]
        result=repeat.summarize(rows)
        self.assertEqual(result['total'],5)
        self.assertEqual(result['valid'],3)
        self.assertEqual(result['distinct'],2)
        self.assertEqual(result['errors'],1)
        self.assertEqual(result['empty'],1)
        self.assertAlmostEqual(result['ratio'],2/3)
        self.assertEqual(result['cells'][0]['most_repeated'],2)

    def test_category_and_empty_inputs(self):
        rows=[dict(char='灯',scenario='a',cat='x',reply='甲'),
              dict(char='灯',scenario='a',cat='y',reply='乙')]
        self.assertEqual(repeat.summarize(rows,'x')['valid'],1)
        self.assertIsNone(repeat.summarize(rows,'missing')['ratio'])
        self.assertIsNone(repeat.summarize([])['ratio'])
