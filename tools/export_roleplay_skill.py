"""从角色 SSOT 导出可携带的扮演 Skill；不调用模型，不复制语料。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from _paths import ROOT, REPORT

sys.path.insert(0, str(ROOT))

from idiolect import __version__
from idiolect.registry import _PACKAGE_NAMES, get_canon_profile, get_voice_manifest
from idiolect.scene_length_targets import SCENE_LENGTH_TARGETS
from idiolect.style_target import build_style_target_block

SOURCE = ROOT / 'skills' / 'mygo-five-roleplay'


def render_files() -> dict[str, str]:
    """发布副本由源码重建，禁止成为另一套手写角色设定。"""
    files = {'SKILL.md': (SOURCE / 'SKILL.md').read_bytes().decode('utf-8')}
    for name in ('LICENSE', 'NOTICE.md'):
        files[name] = (ROOT / name).read_bytes().decode('utf-8')
    roles = []
    for char, module in _PACKAGE_NAMES.items():
        key = module.split('.')[-2]
        base = f'references/{key}'
        canon, voice = get_canon_profile(char), get_voice_manifest(char)
        if not canon.strip() or not voice.strip():
            raise ValueError(f'{char} 的 canon/voice 缺失，拒绝发布不完整角色包')
        files[f'{base}/persona.md'] = (
            f'# {char}：身份与表达\n\n'
            '本文件由角色源码导出。只在选中本角色时读取；不要手改生成内容。\n\n'
            f'## canon\n\n{canon.strip()}\n\n## voice\n\n{voice.strip()}\n')
        parts = [f'# {char}：说话尺度',
                 '先读取默认尺度；场景明确时只参考对应小节。标题用于检索，不应进入角色台词。',
                 '这是中文目标的声明式参考，不执行 Python 路由、session 去重或 voice_check。',
                 '## 默认', build_style_target_block(char, '')]
        for scene, target in SCENE_LENGTH_TARGETS.get(char, {}).items():
            parts.extend([f"## {scene} · {target['cn']}", build_style_target_block(char, scene)])
        files[f'{base}/targets.md'] = '\n\n'.join(parts) + '\n'
        roles.append({'name': char, 'key': key, 'directory': base})
    files['manifest.json'] = json.dumps({
        'schema_version': 1, 'idiolect_version': __version__, 'roles': roles,
        'mode': 'agent-declarative',
        'runtime_equivalence': False,
        'sha256': {name: hashlib.sha256(body.encode('utf-8')).hexdigest()
                   for name, body in sorted(files.items())},
    }, ensure_ascii=False, indent=2) + '\n'
    return files


def export(destination: Path, *, check: bool = False) -> list[str]:
    files = render_files()
    mismatches = []
    for name, body in files.items():
        path = destination / name
        current = path.read_bytes().decode('utf-8') if path.exists() else None
        if current != body:
            mismatches.append(name)
    if check:
        return mismatches
    # 发布时拒绝覆盖不同内容，避免把旧手改资料或用户文件静默抹掉。
    conflicts = [name for name in mismatches if (destination / name).exists()]
    if conflicts:
        raise ValueError('目标含不同内容，请使用新的输出目录：' + ', '.join(conflicts))
    for name in mismatches:
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[name], encoding='utf-8', newline='\n')
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=REPORT / 'mygo-five-roleplay',
                        help='完整 Skill 的输出目录；默认 report/mygo-five-roleplay')
    parser.add_argument('--check', action='store_true', help='只校验目标与当前源码是否一致')
    args = parser.parse_args()
    try:
        differences = export(args.out, check=args.check)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'[skill] {exc}\n')
    if args.check and differences:
        print('[skill] 不一致：' + ', '.join(differences))
        return 1
    print(f'[skill] {"校验通过" if args.check else "导出完成"}：{args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
