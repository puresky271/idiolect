"""可选的密钥注入垫片。

原项目从 `.streamlit/secrets.toml` 读密钥再灌进进程环境；本仓库直接读环境变量，
这里保留同名函数只为让 `tools/probe/probe_runner.py` 不用改。

支持两种可选来源（都没有就什么都不做）：
  · 仓库根的 `.env`（`KEY=VALUE` 每行一条）
  · 仓库根的 `.streamlit/secrets.toml`（取顶层 `KEY = "VALUE"`）

已存在的环境变量不会被覆盖。
"""
from __future__ import annotations

# ── idiolect 路径引导（可移植）：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import os
import re
from pathlib import Path

_KV = re.compile(r"^\s*([A-Za-z_][\w]*)\s*[=:]\s*[\"\']?([^\"\'#\n]*)")


def sync_env_from_secrets() -> int:
    """返回注入的变量个数。幂等，且不覆盖已有环境变量。"""
    n = 0
    for path in (ROOT / ".env", ROOT / ".streamlit" / "secrets.toml"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _KV.match(line)
            if not m:
                continue
            key, value = m.group(1), m.group(2).strip()
            if value and not os.environ.get(key):
                os.environ[key] = value
                n += 1
    return n
