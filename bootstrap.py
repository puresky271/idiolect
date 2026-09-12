"""一条命令把这份仓库装成能跑的状态。

给你手上刚拿到的那份副本用（clone 下来 / 解压出来 / npx degit 拉下来都行）：

    python bootstrap.py                 # 建 .venv、装依赖、跑体检、打印一份 prompt
    python bootstrap.py --no-tools      # 只要装配库（零第三方依赖），不装工具链
    python bootstrap.py --char Rana --msg "你今天又想去哪找猫"

它只做四件事，每步都会打印自己在干什么：

    1. 检查 Python 版本（需要 3.11+）
    2. 在仓库根建 .venv（已存在就复用）
    3. 装依赖：默认 requirements.txt；--no-tools 时只 `pip install -e .`
    4. 跑 `tools/offline_smoke.py --fast` 自检，并打印一个角色的四层字数

不改动仓库里的任何已跟踪文件；`.venv/` 已在 .gitignore 里。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_PY = (3, 11)


def say(step: str, msg: str = "") -> None:
    print(f"[bootstrap] {step}{('：' + msg) if msg else ''}", flush=True)


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(argv: list[str], **kw) -> int:
    print(f"    $ {' '.join(str(a) for a in argv)}", flush=True)
    return subprocess.run(argv, cwd=ROOT, **kw).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="把 idiolect 装成能跑的状态")
    ap.add_argument("--no-tools", action="store_true",
                    help="不装工具链依赖，只装运行时包（零第三方依赖）")
    ap.add_argument("--venv", default=".venv", help="虚拟环境目录（默认 .venv）")
    ap.add_argument("--char", default="Rana", help="最后打印这个角色的四层字数")
    ap.add_argument("--msg", default="你今天又想去哪找猫", help="配合 --char 的那句话")
    ap.add_argument("--skip-smoke", action="store_true", help="跳过 offline_smoke 自检")
    args = ap.parse_args()

    if sys.version_info < MIN_PY:
        say("stop", f"需要 Python {MIN_PY[0]}.{MIN_PY[1]}+，当前是 "
                    f"{sys.version_info.major}.{sys.version_info.minor}")
        return 2
    say("python", f"{sys.version.split()[0]}（{sys.executable}）")

    venv = ROOT / args.venv
    py = venv_python(venv)
    if py.exists():
        say("venv", f"复用已有的 {venv}")
    else:
        say("venv", f"创建 {venv}")
        if run([sys.executable, "-m", "venv", str(venv)]) != 0:
            say("stop", "建 venv 失败——也可以跳过它，直接 `pip install -e .` 装到当前环境")
            return 2

    say("deps", "只装运行时包（零第三方依赖）" if args.no_tools else "装 requirements.txt")
    target = ["-e", "."] if args.no_tools else ["-r", "requirements.txt"]
    if run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"]) != 0:
        say("warn", "升级 pip 失败，继续")
    if run([str(py), "-m", "pip", "install", "-q", *target]) != 0:
        say("stop", "装依赖失败。离线环境可以先只装运行时包：python bootstrap.py --no-tools")
        return 2

    if not args.skip_smoke:
        say("smoke", "跑 tools/offline_smoke.py --fast（不调 LLM、不写仓库文件）")
        if run([str(py), "-X", "utf8", "tools/offline_smoke.py", "--fast"]) != 0:
            say("warn", "自检没过。多数情况是缺语料或某个依赖没装上；"
                        "`tools/offline_smoke.py`（不带 --fast）会给出更细的项")
    else:
        say("smoke", "按参数跳过")

    say("prompt", f"{args.char} 的四层字数")
    run([str(py), "-X", "utf8", "-m", "idiolect", "sizes", args.char, args.msg])

    activate = (f"{venv}\\Scripts\\activate" if os.name == "nt" else f"source {venv}/bin/activate")
    print()
    say("done", "好了。接下来：")
    print(f"    激活环境： {activate}")
    print(f"    看 prompt： {py} -X utf8 -m idiolect prompt {args.char} \"{args.msg}\"")
    print(f"    跑体检：   {py} -X utf8 tools/offline_smoke.py")
    print(f"    换别的角色：读 .claude/skills/idiolect-pipeline/（语料 → 蒸馏 → 角色包 → 评测）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
