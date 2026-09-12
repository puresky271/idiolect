"""mock 时钟：评测与探针的唯一时间源。

硬规矩是「**所有 LLM 测试都在 mock 白天时间下跑**」。理由不是洁癖：
角色对「现在」是敏感的——乐奈犯困、立希夜猫子、灯深夜不安，同一句话在
15:00 和 03:00 会命中不同的 turn_logic 与长度指引。拿真实时钟跑评测，等于
让「今天是几点」变成实验里的隐藏变量，跨批次数据就不可比了。

本仓库没有世界日历、没有日程模拟，只保留这条约定本身：**任何会读「现在」的
路径都从本模块取时间**，不要直接 `datetime.now()`。

    from mock_clock import mock_now
    block = render_turn_special_block("乐奈", text, now_jst=mock_now())

约定：

  · 默认 `2026-09-12T15:00:00+09:00`——一个普通的周六下午，五人都在线的白天；
  · `IDIOLECT_MOCK_NOW` 覆盖（ISO 8601；无时区按 JST 解释）；
  · `IDIOLECT_MOCK_NOW=real`（或 `--real`）走真实时钟——只用于人工观察，
    不要用它跑评测或门禁，产出的数字不可与他人比较。

命令行：

    py -X utf8 tools/mock_clock.py                 # 打印当前生效的时间与来源
    py -X utf8 tools/mock_clock.py --set 2026-09-12T03:00:00+09:00
    py -X utf8 tools/mock_clock.py --real
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# 默认 mock 时刻：白天、非睡眠、非深夜场景
DEFAULT_MOCK_ISO = "2026-09-12T15:00:00+09:00"

ENV_VAR = "IDIOLECT_MOCK_NOW"

_REAL_TOKENS = {"real", "now", "off", "0", "false", "no"}


def parse_spec(spec: str) -> datetime | None:
    """把 spec 解析成 JST datetime；`real`/空 等返回 None（= 用真实时钟）。"""
    raw = str(spec or "").strip()
    if not raw or raw.lower() in _REAL_TOKENS:
        return None
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"{ENV_VAR}={spec!r} 不是合法 ISO 8601 时间（例：2026-09-12T15:00:00+09:00）"
        ) from exc
    return dt.replace(tzinfo=JST) if dt.tzinfo is None else dt.astimezone(JST)


def is_mocked() -> bool:
    """当前是否处于 mock（pinned）时间。未设置 env = 默认 mock，返回 True。"""
    spec = os.environ.get(ENV_VAR, "").strip()
    return True if not spec else parse_spec(spec) is not None


def real_now() -> datetime:
    return datetime.now(JST)


def mock_now() -> datetime:
    """当前生效的「现在」（JST，带时区）。

    默认返回固定的 mock 白天时刻；`IDIOLECT_MOCK_NOW=real` 时才返回真实时间。
    """
    spec = os.environ.get(ENV_VAR, "").strip()
    pinned = parse_spec(spec) if spec else parse_spec(DEFAULT_MOCK_ISO)
    return pinned if pinned is not None else real_now()


def describe() -> str:
    spec = os.environ.get(ENV_VAR, "").strip()
    dt = mock_now()
    if not spec:
        return f"mock {dt.isoformat()}（默认；{ENV_VAR} 未设置）"
    if parse_spec(spec) is None:
        return f"REAL {dt.isoformat()}（{ENV_VAR}={spec}）——评测不要用"
    return f"mock {dt.isoformat()}（{ENV_VAR}={spec}）"


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="mock 时钟（评测统一时间源）",
        epilog="注意：--set / --real / --shell 只**打印**要设的环境变量，"
               "不会改变当前 shell（子进程改不了父进程的环境）。把那一行贴进 shell 才生效。")
    ap.add_argument("--set", dest="set_iso", default="", help="pinned 时刻（ISO 8601）")
    ap.add_argument("--real", action="store_true", help="改用真实时钟（不要跑评测）")
    ap.add_argument("--shell", action="store_true", help="打印可直接 set 的环境变量行")
    args = ap.parse_args()

    if args.real:
        print(f"$env:{ENV_VAR} = 'real'")
        print("[warn] 真实时钟下跑出来的数字不能与 mock 批次比较："
              "时段会变成隐藏变量（见 docs/04-evaluation.md 第 7 节）。")
    elif args.set_iso:
        parse_spec(args.set_iso)  # 校验
        print(f"$env:{ENV_VAR} = '{args.set_iso}'")
    elif args.shell:
        print(f"$env:{ENV_VAR} = '{DEFAULT_MOCK_ISO}'")

    print(f"当前生效：{describe()}")
    if args.set_iso or args.real or args.shell:
        print("        （上面那行是给 shell 用的；本进程没有改变它）")
    return 0


__all__ = ["DEFAULT_MOCK_ISO", "ENV_VAR", "JST", "describe", "is_mocked", "mock_now", "parse_spec", "real_now"]

if __name__ == "__main__":
    raise SystemExit(main())
