"""独立目录里的 Skill 必须携带真实角色资料，且不能覆盖不同内容。"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('roleplay_export', ROOT / 'tools/export_roleplay_skill.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class RoleplayExportTests(unittest.TestCase):
    def test_portable_contents_match_sources_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'skill'
            exporter.export(dest)
            manifest = json.loads((dest / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(len(manifest['roles']), 5)
            self.assertFalse(manifest['runtime_equivalence'])
            for role in manifest['roles']:
                persona = (dest / role['directory'] / 'persona.md').read_text(encoding='utf-8')
                self.assertIn(exporter.get_canon_profile(role['name']).strip(), persona)
                self.assertIn(exporter.get_voice_manifest(role['name']).strip(), persona)
                self.assertTrue((dest / role['directory'] / 'targets.md').is_file())
            for name, digest in manifest['sha256'].items():
                self.assertEqual(hashlib.sha256((dest / name).read_bytes()).hexdigest(), digest)
            self.assertEqual(exporter.export(dest, check=True), [])

    def test_check_detects_drift_and_export_preserves_modified_file(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)
            exporter.export(dest)
            target = dest / 'references/rana/persona.md'
            target.write_text('user changes', encoding='utf-8')
            self.assertIn('references/rana/persona.md', exporter.export(dest, check=True))
            with self.assertRaises(ValueError):
                exporter.export(dest)
            self.assertEqual(target.read_text(encoding='utf-8'), 'user changes')
