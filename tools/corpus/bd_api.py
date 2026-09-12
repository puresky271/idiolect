"""Bestdori 资产访问层（语料抓取专用，只读）。

链路（与 zyf722/bestdori-voice-extractor 一致，但不需要下载 14GB 语音）：
  - 目录树:  https://bestdori.com/api/explorer/{locale}/assets/_info.json
  - 子目录:  https://bestdori.com/api/explorer/{locale}/assets/{prefix}/{dir}.json  -> [filename, ...]
  - 资产:    https://bestdori.com/assets/{locale}/{prefix}/{dir}_rip/{filename}
  - 台词:    资产 JSON 的 Base.talkData[]，每条 {body, voices:[{characterId, voiceId}]}

只要 .asset（JSON 剧本），不要 mp3，所以成本是 MB 级而非 GB 级。
"""
from __future__ import annotations

# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import json
import time
from typing import Any, Iterable

import requests

BASE = "https://bestdori.com"
MYGO = {"36": "tomori", "37": "anon", "38": "rana", "39": "soyo", "40": "taki"}
MYGO_ID_TO_CN = {"36": "灯", "37": "爱音", "38": "乐奈", "39": "爽世", "40": "立希"}

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (idiolect corpus fetch; read-only)"})
try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    _adapter = HTTPAdapter(
        max_retries=Retry(total=4, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504]),
        pool_connections=16,
        pool_maxsize=16,
    )
    _session.mount("http://", _adapter)
    _session.mount("https://", _adapter)
except Exception:  # pragma: no cover - 环境缺 urllib3 时退化为无重试
    pass


def get_json(url: str, *, retries: int = 3, timeout: int = 40) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = _session.get(url, timeout=timeout)
            if r.status_code == 404:
                raise FileNotFoundError(url)
            r.raise_for_status()
            return r.json()
        except FileNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"GET failed {url}: {last}")


def info(locale: str = "jp") -> dict:
    return get_json(f"{BASE}/api/explorer/{locale}/assets/_info.json", timeout=90)


def listing(prefix: tuple[str, ...], directory: str, locale: str = "jp") -> list[str]:
    """目录清单；404 视为空目录。"""
    path = "/".join((*prefix, directory)) if prefix else directory
    try:
        data = get_json(f"{BASE}/api/explorer/{locale}/assets/{path}.json")
    except FileNotFoundError:
        return []
    return data if isinstance(data, list) else []


def asset_url(prefix: tuple[str, ...], directory: str, filename: str, locale: str = "jp") -> str:
    p = "/".join(prefix)
    return f"{BASE}/assets/{locale}/{p}/{directory}_rip/{filename}"


def get_asset(prefix: tuple[str, ...], directory: str, filename: str, locale: str = "jp") -> Any:
    return get_json(asset_url(prefix, directory, filename, locale))


def walk_dirs(node: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    """深度优先展开 _info.json 子树，产出 (目录前缀, 该目录的文件数字典)。

    叶子是 dict[str, int]（filename -> count，或子目录名 -> count），
    与真正的目录清单需用 listing() 二次确认。
    """
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk_dirs(value, (*path, key))


def iter_assets(prefix: tuple[str, ...], directory: str, locale: str = "jp") -> Iterable[tuple[str, Any]]:
    """遍历一个目录下所有 .asset 文件，产出 (filename, parsed_json)。"""
    for fn in listing(prefix, directory, locale):
        if not fn.endswith(".asset"):
            continue
        try:
            yield fn, get_asset(prefix, directory, fn, locale)
        except Exception as exc:  # noqa: BLE001
            print(f"    [skip] {directory}/{fn}: {type(exc).__name__} {exc}")
            continue


def extract_lines(asset: Any) -> list[dict]:
    """从 .asset JSON 抽出台词：每条 (characterId, voiceId, text, speaker)。

    结构: Base.talkData[] = {
        body: str,                       # 台词正文
        windowDisplayName: str,          # 显示名（如「燈」「楽奈の母」）
        talkCharacters: [{characterId}], # 真正说话的人
        voices: [{characterId, voiceId}],# 配音（常为空 → 不能只看 voices）
    }
    一条 body 可能挂多个 voices（多人同句），逐 voice 展开、按 characterId 归属；
    voices 为空时回落到 talkCharacters，否则该行会整条丢失。
    """
    out: list[dict] = []
    if not isinstance(asset, dict):
        return out
    base = asset.get("Base")
    if not isinstance(base, dict):
        return out
    for talk in base.get("talkData") or []:
        if not isinstance(talk, dict):
            continue
        body = (talk.get("body") or "").replace("\n", "").strip()
        if not body:
            continue
        speaker = (talk.get("windowDisplayName") or "").strip()
        voices = [v for v in (talk.get("voices") or []) if isinstance(v, dict) and v.get("characterId") is not None]
        if voices:
            pairs = [(str(v["characterId"]), v.get("voiceId")) for v in voices]
        else:
            pairs = [
                (str(c["characterId"]), None)
                for c in (talk.get("talkCharacters") or [])
                if isinstance(c, dict) and c.get("characterId") is not None
            ]
        for cid, vid in pairs:
            out.append({"character_id": cid, "voice_id": vid, "text": body, "speaker": speaker})
    return out
