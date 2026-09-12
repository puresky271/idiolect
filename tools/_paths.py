"""路径解析（所有工具的**唯一**路径来源）。

移植自 mygo_chat 的 bench 目录：原脚本各自用 `HERE / "raw" / "gold"` 与 `HERE / "report"`
拼路径，散在几十个文件里。搬过来之后收成一处，并允许用环境变量指向别处。

约定：

  · `ROOT`        —— 仓库根
  · `CORPUS_DIR`  —— 原作语料目录（**不入库**，需自己跑 `tools/corpus/` 生成）
                     默认 `<repo>/raw/gold`，可用 `IDIOLECT_CORPUS_DIR` 覆盖
  · `REPORT`      —— 探针与评分的产物目录（gitignored），默认 `<repo>/report`
  · `DATA`        —— 随仓库发布的派生统计，默认 `<repo>/data`

语料文件格式：每行一个 JSON 对象，字段
`{"character": <角色 key>, "text": <台词>, "split": "train"|"test", ...}`。
`character` 用罗马字 key（`anon` / `soyo` / `tomori` / `taki` / `rana`）。
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env_path(name: str, default: Path) -> Path:
    raw = str(os.environ.get(name, "") or "").strip()
    return Path(raw) if raw else default


CORPUS_DIR = _env_path("IDIOLECT_CORPUS_DIR", ROOT / "raw" / "gold")
REPORT = _env_path("IDIOLECT_REPORT_DIR", ROOT / "report")
DATA = _env_path("IDIOLECT_DATA_DIR", ROOT / "data")


def corpus_file(lang: str = "cn") -> Path:
    """某个语言的语料文件路径。缺失时抛 FileNotFoundError（附上补齐方法）。"""
    p = CORPUS_DIR / f"{lang}.jsonl"
    if not p.exists():
        raise FileNotFoundError(
            f"找不到语料 {p}。本仓库不分发原作文本，请先跑 tools/corpus/ 抓取，"
            f"或用 IDIOLECT_CORPUS_DIR 指向已有语料目录（见 docs/02-corpus.md）。"
        )
    return p


def ensure_dirs() -> None:
    REPORT.mkdir(parents=True, exist_ok=True)


__all__ = ["CORPUS_DIR", "DATA", "REPORT", "ROOT", "corpus_file", "ensure_dirs"]
