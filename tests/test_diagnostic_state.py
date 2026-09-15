"""诊断不得消费真实去重状态，也不能回滚其他线程的更新。"""
from datetime import datetime
import threading
import unittest
from idiolect import scene_engine as se
from idiolect.assemble import _build_layers, layer_sizes


class DiagnosticStateTests(unittest.TestCase):
    def test_repeated_size_queries_preserve_next_real_turn(self):
        now=datetime.fromisoformat('2026-09-12T15:00:00+09:00')
        for char in ('爱音','灯','立希','素世','乐奈'):
            with self.subTest(char=char):
                sid='diagnostic-contract:'+char
                first=layer_sizes(char,'你今天又想去哪找猫',session_id=sid,now=now)
                second=layer_sizes(char,'你今天又想去哪找猫',session_id=sid,now=now)
                actual=_build_layers(char,'你今天又想去哪找猫',session_id=sid,now=now)
                self.assertEqual(first,second)
                self.assertEqual(first,{k:len(actual.get(k,'')) for k in first})

    def test_nested_values_and_other_thread_updates_are_isolated(self):
        store=se.SessionValues()
        live={'items':[1]}
        store.put('live',live)
        marks=se.SessionStore()
        marks.mark('existing','once')
        with se.isolated_session_state():
            self.assertTrue(marks.has('existing','once'))
            store.peek('live')['items'].append(2)
            marks.mark('preview','once')
            with se.isolated_session_state():
                store.peek('live')['items'].append(3)
            self.assertEqual(store.peek('live')['items'],[1,2])
            thread=threading.Thread(target=lambda: marks.mark('concurrent','once'))
            thread.start()
            thread.join()
        self.assertEqual(live,{'items':[1]})
        self.assertFalse(marks.has('preview','once'))
        self.assertTrue(marks.has('concurrent','once'))

    def test_exception_discards_preview(self):
        marks=se.SessionStore()
        with self.assertRaises(RuntimeError):
            with se.isolated_session_state():
                marks.mark('preview','once')
                raise RuntimeError('stop')
        self.assertFalse(marks.has('preview','once'))
