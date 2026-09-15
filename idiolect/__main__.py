"""命令行入口：`python -m idiolect <命令>`。

装完包（`pip install .`）之后，不克隆仓库、不需要语料也能用的最小演示：

  list                          列出内置的五个示例角色
  prompt <角色> <用户的话>       打印这一刻装配出的完整 system prompt
  sizes  <角色> <用户的话>       只打印四层各自的字符数
  showcase <用户的话>           并排查看五人命中的场景与四层预算
  chat   <角色> <用户的话>       走 OpenAI 兼容端点真实对话一轮
                                （读环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，
                                 需要 `pip install "idiolect[llm]"`）

角色名支持别名：`乐奈` / `rana` / `要乐奈` 等价（完整别名表见 `idiolect/registry.py`）。
"""
from __future__ import annotations

import argparse
import os
import sys

from . import assemble as _assembly
from .assemble import LAYER_ORDER, build_messages, build_system_prompt, layer_sizes
from .registry import canonicalize_name, postprocess_reply
from .scene_classifier import classify

# canonical 名 → 一句可检验的风格数字（数据源：idiolect/style_target.py 的 STYLE_TARGETS）
_CHARACTERS = ("爱音", "灯", "立希", "素世", "乐奈")
_STYLE_HINTS = {
    "爱音": "反应快、外放，容易把话题推向具体行动",
    "灯": "停顿多、感受细，常用不完整的短句",
    "立希": "短促直接，先处理眼前的问题",
    "素世": "克制柔和，措辞留有余地",
    "乐奈": "极短、跳跃，容易被猫和当下兴趣带走",
}


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
    if args.layers is not None:
        wanted = {k.strip() for k in args.layers.split(",") if k.strip()}
        unknown = wanted.difference(LAYER_ORDER)
        if not wanted or unknown:
            print(f"无效的层选择：{args.layers!r}；可用：{','.join(LAYER_ORDER)}", file=sys.stderr)
            return 2
        # 动态模块会消费会话状态；分层视图只能装配一次。
        blocks = _assembly._build_layers(
            char, args.text, include_turn_logic=not args.no_turn_logic)
        for key in LAYER_ORDER:
            if key in wanted and blocks.get(key, "").strip():
                print(f"── {key} ──\n{blocks[key].strip()}\n")
        return 0
    system = build_system_prompt(
        char, args.text,
        include_turn_logic=not args.no_turn_logic)
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


def _cmd_showcase(args: argparse.Namespace) -> int:
    """不调用模型的五人并排展示，作为首次接触和评测前置检查。"""
    text = args.text.strip()
    if not text:
        print("请提供一句用户输入，例如：idiolect showcase \"我今天有点撑不住了\"", file=sys.stderr)
        return 2
    print("idiolect 五人展示（只读装配，不调用模型）")
    print(f"用户输入：{text}\n")
    print(f"{'角色':<6}{'命中场景':<18}{'四层合计':>10}  风格提示")
    print("-" * 76)
    for char in _CHARACTERS:
        scene = classify(text, char) or "（无专属场景）"
        total = sum(layer_sizes(char, text).values())
        print(f"{char:<6}{scene:<18}{total:>8} 字  {_STYLE_HINTS[char]}")
    print("\n下一步：")
    print("  体验：将本仓库的 skills/mygo-five-roleplay/ 交给 Claude 或 Codex，先选择角色。")
    print("  解释：idiolect prompt <角色> <同一句输入>")
    print("  评测：py -X utf8 tools/probe/probe_runner.py --help")
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
    violations = cleaned.get("violations") or {}
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
    p_prompt.add_argument("--layers", default=None, help="只打印指定层，逗号分隔（canon,voice,style_target,turn_logic）")
    p_prompt.add_argument("--no-turn-logic", action="store_true", help="不注入本轮场景指引")

    p_sizes = sub.add_parser("sizes", help="打印四层各自的字符数")
    p_sizes.add_argument("char")
    p_sizes.add_argument("text")

    p_showcase = sub.add_parser("showcase", help="并排查看五人命中的场景与四层预算（不调用模型）")
    p_showcase.add_argument("text")

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
    if args.cmd == "showcase":
        return _cmd_showcase(args)
    if args.cmd == "chat":
        return _cmd_chat(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
