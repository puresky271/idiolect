"""命令行入口：`python -m idiolect <命令>`。

装完包（`pip install .`）之后，不克隆仓库、不需要语料也能用的最小演示：

  list                          列出内置的五个示例角色
  prompt <角色> <用户的话>       打印这一刻装配出的完整 system prompt
  sizes  <角色> <用户的话>       只打印四层各自的字符数
  chat   <角色> <用户的话>       走 OpenAI 兼容端点真实对话一轮
                                （读环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，
                                 需要 `pip install "idiolect[llm]"`）

角色名支持别名：`乐奈` / `rana` / `要乐奈` 等价（完整别名表见 `idiolect/registry.py`）。
"""
from __future__ import annotations

import argparse
import os
import sys

from .assemble import LAYER_ORDER, build_messages, build_system_prompt, layer_sizes
from .registry import canonicalize_name, postprocess_reply
from .scene_classifier import classify

# canonical 名 → 一句可检验的风格数字（数据源：idiolect/style_target.py 的 STYLE_TARGETS）
_CHARACTERS = ("爱音", "灯", "立希", "素世", "乐奈")


def _cmd_list() -> int:
    print("内置示例角色（《BanG Dream! It's MyGO!!!!!》）：")
    for name in _CHARACTERS:
        print(f"  {name}")
    print("\n别名示例：rana / 要乐奈 / 楽奈 → 乐奈；完整表见 idiolect/registry.py")
    return 0


def _resolve(char: str) -> str:
    name = canonicalize_name(char)
    if not name:
        print(f"不认识的角色：{char!r}（可用：{'、'.join(_CHARACTERS)}，或别名）", file=sys.stderr)
        raise SystemExit(2)
    return name


def _cmd_prompt(args: argparse.Namespace) -> int:
    char = _resolve(args.char)
    system = build_system_prompt(
        char, args.text,
        include_turn_logic=not args.no_turn_logic)
    if args.layers:
        wanted = {k.strip() for k in args.layers.split(",") if k.strip()}
        from .registry import get_canon_profile, get_voice_manifest, render_turn_special_block
        from .style_target import build_style_target_block
        blocks = {
            "canon": get_canon_profile(char),
            "voice": get_voice_manifest(char),
            "style_target": build_style_target_block(char, classify(args.text, char)),
            "turn_logic": render_turn_special_block(char, args.text),
        }
        for key in LAYER_ORDER:
            if key in wanted and blocks[key].strip():
                print(f"── {key} ──\n{blocks[key].strip()}\n")
        return 0
    scene = classify(args.text, char)
    if scene:
        print(f"# 命中场景：{scene}\n", file=sys.stderr)
    print(system)
    return 0


def _cmd_sizes(args: argparse.Namespace) -> int:
    char = _resolve(args.char)
    sizes = layer_sizes(char, args.text)
    for key in LAYER_ORDER:
        print(f"{key:<14}{sizes.get(key, 0):>8} 字")
    print(f"{'合计':<14}{sum(sizes.values()):>8} 字")
    return 0


def _cmd_chat(args: argparse.Namespace) -> int:
    char = _resolve(args.char)
    try:
        from openai import OpenAI
    except ImportError:
        print("chat 需要 openai 库：pip install \"idiolect[llm]\"（或 pip install openai）",
              file=sys.stderr)
        return 2
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip()
    if not (api_key and base_url and model):
        print("请先设置环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL", file=sys.stderr)
        return 2

    messages = build_messages(char, args.text)
    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model, messages=messages,
        temperature=args.temperature, max_tokens=args.max_tokens)
    raw = resp.choices[0].message.content or ""
    cleaned = postprocess_reply(char, raw)
    print(cleaned["text"])
    violations = cleaned.get("violations") or []
    if violations:
        print(f"\n# voice_check 修过 {len(violations)} 处：{violations}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m idiolect",
        description="把角色的说话方式装配成 system prompt（示例角色：MyGO!!!!! 五人）")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出内置示例角色")

    p_prompt = sub.add_parser("prompt", help="打印装配出的完整 system prompt")
    p_prompt.add_argument("char")
    p_prompt.add_argument("text")
    p_prompt.add_argument("--layers", default="", help="只打印指定层，逗号分隔（canon,voice,style_target,turn_logic）")
    p_prompt.add_argument("--no-turn-logic", action="store_true", help="不注入本轮场景指引")

    p_sizes = sub.add_parser("sizes", help="打印四层各自的字符数")
    p_sizes.add_argument("char")
    p_sizes.add_argument("text")

    p_chat = sub.add_parser("chat", help="走 OpenAI 兼容端点真实对话一轮")
    p_chat.add_argument("char")
    p_chat.add_argument("text")
    p_chat.add_argument("--temperature", type=float, default=0.75)
    p_chat.add_argument("--max-tokens", type=int, default=420)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        return _cmd_list()
    if args.cmd == "prompt":
        return _cmd_prompt(args)
    if args.cmd == "sizes":
        return _cmd_sizes(args)
    if args.cmd == "chat":
        return _cmd_chat(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
