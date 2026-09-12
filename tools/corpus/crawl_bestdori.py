"""爬取 Bestdori 剧本资产 → 抽取 MyGO 五人台词 → 落盘按角色分档语料。

设计要点：
  - 只取 .asset（JSON 剧本），不下 mp3：成本 MB 级。
  - 只保留 characterId ∈ 36..40（燈/愛音/楽奈/そよ/立希）。
  - 支持断点续跑：已抓过的 asset 记在 _crawl_done.jsonl，重跑跳过。
  - 并发受限（默认 8），避免把 Bestdori 打挂。

产出：bench/raw/bestdori/{jp,cn}.jsonl
  每行 {"character_id","voice_id","text","source","dir","file"}
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

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bd_api as A  # noqa: E402

# 覆盖度优先；effects 明确排除（非剧本）
BUCKETS: list[tuple[tuple[str, ...], str]] = [
    (("scenario",), "eventstory"),
    (("scenario",), "actionset"),
    (("scenario",), "band"),
    (("scenario",), "birthdaystory"),
    (("scenario",), "main"),
    (("scenario",), "loginstory"),
    (("scenario",), "area_opening_story"),
    (("scenario",), "precedingstory"),
    (("scenario",), "afterlivetalk"),
    (("scenario",), "digeststory"),
    (("scenario",), "backstagestory"),
]

MYGO_IDS = set(A.MYGO)


def build_listing_cache(locale: str, workers: int = 12) -> list[tuple[tuple[str, ...], str, str]]:
    """一次性抓全部目录清单（并发 + 落盘缓存），产出 (prefix, directory, filename)。

    缓存到 raw/bestdori/_listings_{locale}.json，重跑直接复用，
    否则每次枚举要打 ~8600 次 API。
    """
    cache_path = HERE / "raw" / "bestdori" / f"_listings_{locale}.json"
    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        targets = [(tuple(t[0]), t[1], t[2]) for t in data["targets"]]
        print(f"[{locale}] listing cache hit: {len(targets)} targets", flush=True)
        return targets

    info = A.info(locale)
    pairs: list[tuple[tuple[str, ...], str]] = []
    for prefix, directory in BUCKETS:
        node = info
        try:
            for k in prefix:
                node = node[k]
            sub = node.get(directory)
        except Exception:  # noqa: BLE001
            sub = None
        pairs.append((prefix, directory))
        if isinstance(sub, dict):
            for subdir in sub:
                if not subdir.endswith(".asset"):
                    pairs.append(((*prefix, directory), subdir))

    print(f"[{locale}] fetching {len(pairs)} directory listings ...", flush=True)
    listings: dict[str, list[str]] = {}

    def fetch(pair: tuple[tuple[str, ...], str]) -> tuple[str, list[str]]:
        prefix, directory = pair
        key = f"{'/'.join(prefix)}/{directory}"
        try:
            return key, A.listing(prefix, directory, locale)
        except Exception:  # noqa: BLE001
            return key, []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, fut in enumerate(as_completed([pool.submit(fetch, p) for p in pairs]), 1):
            key, files = fut.result()
            listings[key] = files
            if i % 500 == 0:
                print(f"[{locale}] listings {i}/{len(pairs)}", flush=True)

    targets: list[tuple[tuple[str, ...], str, str]] = []
    for key, files in listings.items():
        parts = key.split("/")
        prefix, directory = tuple(parts[:-1]), parts[-1]
        for fn in files:
            if fn.endswith(".asset"):
                targets.append((prefix, directory, fn))
    targets.sort()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"locale": locale, "targets": [[list(t[0]), t[1], t[2]] for t in targets]}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[{locale}] cached {len(targets)} targets -> {cache_path.name}", flush=True)
    return targets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locales", default="jp,cn")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="0 = 全量；>0 只抓前 N 个（冒烟）")
    args = ap.parse_args()

    out_dir = HERE / "raw" / "bestdori"
    out_dir.mkdir(parents=True, exist_ok=True)

    for locale in args.locales.split(","):
        locale = locale.strip()
        if not locale:
            continue
        done_path = out_dir / f"_done_{locale}.jsonl"
        out_path = out_dir / f"{locale}.jsonl"

        done: set[str] = set()
        if done_path.exists():
            for line in done_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    done.add(json.loads(line)["key"])

        print(f"[{locale}] enumerating targets ...", flush=True)
        try:
            targets = build_listing_cache(locale, workers=max(4, args.workers))
        except Exception as exc:  # noqa: BLE001
            print(f"[{locale}] enumerate failed: {type(exc).__name__} {exc}", flush=True)
            continue
        todo = [t for t in targets if f"{'/'.join(t[0])}/{t[1]}/{t[2]}" not in done]
        if args.limit:
            todo = todo[: args.limit]
        print(f"[{locale}] targets={len(targets)} done={len(done)} todo={len(todo)}", flush=True)

        lock = threading.Lock()
        stats = {"ok": 0, "lines": 0, "empty": 0, "fail": 0}

        def work(item: tuple[tuple[str, ...], str, str]) -> tuple[str, list[dict]]:
            prefix, directory, fn = item
            key = f"{'/'.join(prefix)}/{directory}/{fn}"
            try:
                asset = A.get_asset(prefix, directory, fn, locale)
            except Exception:  # noqa: BLE001
                return key, []
            rows = []
            for row in A.extract_lines(asset):
                if row["character_id"] in MYGO_IDS:
                    rows.append({**row, "dir": f"{'/'.join(prefix)}/{directory}", "file": fn})
            return key, rows

        fout = out_path.open("a", encoding="utf-8")
        fdone = done_path.open("a", encoding="utf-8")
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(work, t) for t in todo]
                for i, fut in enumerate(as_completed(futures), 1):
                    key, rows = fut.result()
                    with lock:
                        fdone.write(json.dumps({"key": key}, ensure_ascii=False) + "\n")
                        if rows:
                            for r in rows:
                                fout.write(json.dumps(r, ensure_ascii=False) + "\n")
                            stats["ok"] += 1
                            stats["lines"] += len(rows)
                        else:
                            stats["empty"] += 1
                        if i % 100 == 0:
                            fout.flush()
                            fdone.flush()
                            print(f"[{locale}] {i}/{len(todo)} ok={stats['ok']} lines={stats['lines']}", flush=True)
            fout.flush()
            fdone.flush()
        finally:
            fout.close()
            fdone.close()
        print(f"[{locale}] DONE assets_with_lines={stats['ok']} lines={stats['lines']} empty={stats['empty']}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
