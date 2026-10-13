"""代码风格与注释风格门禁（标准库实现，可进 offline_smoke 与 CI）。

为什么要有它：仓库约定「注释与文档用简体中文、模块 docstring 先写这是什么和为什么」，
但约定只写在 AGENTS.md 里时，新代码一多就会漂。这道门禁把可机械检查的部分钉住；
ruff（CI 的 lint job）负责 pyflakes 一类的代码正确性检查，两者分工不重叠。

检查项（违规即 FAIL，退出码 1）：

  代码格式
    · UTF-8、无 BOM、不出现孤立 CR（CRLF 视为 Windows 检出的换行，按 LF 处理）；
    · 缩进不用 tab，行尾无空白，文件以且仅以一个换行结束；
    · `idiolect/` 与 `tools/` 里有可执行语句的模块写 `from __future__ import annotations`。
  注释风格
    · 每个模块有 docstring，且 docstring 用中文写（至少含一个汉字）；
    · `idiolect/` 运行时包（角色包正文除外）的公开类与公开顶层函数有中文 docstring；
    · 注释以 `# ` 开头（shebang 与 `#:` 除外）；
    · 注释与 docstring 不出现繁体专用字（日文假名与日文汉字不受影响）；
    · 不写纯英文的说明性注释：没有汉字、却有三个以上连续英文单词且不像代码片段的注释。
      `noqa` / `type:` / `pragma` 一类工具指令不算说明性注释。

用法：
    py -X utf8 tools/gates/style_gate.py            # 全仓库
    py -X utf8 tools/gates/style_gate.py --json     # 机器可读
    py -X utf8 tools/gates/style_gate.py path ...   # 只查指定文件/目录
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "report", "raw", ".venv", "venv", "build",
              "dist", ".workbuddy", "node_modules"}
# 繁体专用字：只收简体与日文都不用的字形，避免误伤日文台词与日文汉字
_TRADITIONAL_ONLY = set("這們說會對實關點裡從應來與")
_CJK = re.compile(r"[一-鿿]")
_PRAGMA = re.compile(r"^(noqa|type:|pragma|fmt:|ruff:|pylint:|isort:)", re.I)
_PROSE = re.compile(r"(?:\b[A-Za-z]{2,}\b[ ,']+){3,}[A-Za-z]{2,}")
_CODE_HINT = re.compile(r"[=|{}\[\]()<>→←/\\_.:;`\"*+@#$%^&~0-9-]")
# 角色包正文是 prompt 素材，公开函数多是数据访问器；docstring 规则只管运行时核心与评测包
_PUBLIC_DOC_EXEMPT = ("idiolect/characters/",)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def iter_files(targets: list[str]) -> list[Path]:
    paths = [Path(t).resolve() for t in targets] if targets else [ROOT]
    out: list[Path] = []
    for base in paths:
        if base.is_file() and base.suffix == ".py":
            out.append(base)
            continue
        for path in sorted(base.rglob("*.py")):
            if not any(part in _SKIP_DIRS for part in path.relative_to(ROOT).parts):
                out.append(path)
    return out


def _is_prose_comment(body: str) -> bool:
    if _CJK.search(body) or _PRAGMA.match(body):
        return False
    match = _PROSE.search(body)
    if not match:
        return False
    return not _CODE_HINT.search(body)


def check_file(path: Path) -> list[dict]:
    rel = _rel(path)
    issues: list[dict] = []

    def add(line: int, code: str, msg: str) -> None:
        issues.append({"file": rel, "line": line, "code": code, "message": msg})

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        add(1, "bom", "文件带 UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        add(1, "encoding", f"不是 UTF-8：{exc}")
        return issues
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        add(1, "lone_cr", "出现孤立的 CR 换行")
    if text and not text.endswith("\n"):
        add(text.count("\n") + 1, "final_newline", "文件末尾缺换行")
    if text.endswith("\n\n"):
        add(text.count("\n"), "final_newline", "文件末尾有多余空行")
    for lineno, line in enumerate(text.split("\n"), 1):
        if line != line.rstrip(" \t"):
            add(lineno, "trailing_ws", "行尾空白")
        indent = line[: len(line) - len(line.lstrip(" \t"))]
        if "\t" in indent:
            add(lineno, "tab_indent", "缩进使用 tab")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        add(exc.lineno or 1, "syntax", f"语法错误：{exc.msg}")
        return issues

    doc = ast.get_docstring(tree)
    if not doc:
        add(1, "module_docstring", "模块缺 docstring（先写这是什么、为什么）")
    elif not _CJK.search(doc):
        add(1, "docstring_language", "模块 docstring 应使用简体中文")
    has_code = any(not (isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant))
                   for node in tree.body)
    if has_code and rel.startswith(("idiolect/", "tools/")) and "from __future__ import annotations" not in text:
        add(1, "future_annotations", "缺 `from __future__ import annotations`")

    if rel.startswith("idiolect/") and not rel.startswith(_PUBLIC_DOC_EXEMPT):
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and not node.name.startswith("_"):
                ndoc = ast.get_docstring(node)
                if not ndoc:
                    add(node.lineno, "public_docstring", f"公开的 {node.name} 缺 docstring")
                elif not _CJK.search(ndoc.split("\n", 1)[0]):
                    add(node.lineno, "docstring_language", f"{node.name} 的 docstring 首行应使用中文")

    docstrings = [doc or ""]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstrings.append(ast.get_docstring(node) or "")
    for d in docstrings:
        bad = sorted({ch for ch in d if ch in _TRADITIONAL_ONLY})
        if bad:
            add(1, "traditional_chars", f"docstring 出现繁体专用字 {''.join(bad)}")
            break

    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type != tokenize.COMMENT:
            continue
        lineno, comment = tok.start[0], tok.string
        if lineno == 1 and comment.startswith("#!"):
            continue
        if not re.match(r"#(?: |$)", comment) and not comment.startswith("#:"):
            add(lineno, "comment_marker", "注释应以 `# ` 开头")
        body = comment.lstrip("#").strip()
        bad = sorted({ch for ch in body if ch in _TRADITIONAL_ONLY})
        if bad:
            add(lineno, "traditional_chars", f"注释出现繁体专用字 {''.join(bad)}")
        if _is_prose_comment(body):
            add(lineno, "comment_language", f"纯英文说明性注释，请用简体中文：{body[:60]}")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="代码风格与注释风格门禁（标准库）")
    ap.add_argument("paths", nargs="*", help="只检查这些文件/目录（默认全仓库）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    files = iter_files(args.paths)
    issues = [issue for path in files for issue in check_file(path)]
    if args.json:
        print(json.dumps({"files": len(files), "issues": issues}, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print(f"{issue['file']}:{issue['line']}: {issue['code']} {issue['message']}")
        counts: dict[str, int] = {}
        for issue in issues:
            counts[issue["code"]] = counts.get(issue["code"], 0) + 1
        verdict = "PASS" if not issues else "FAIL"
        print(f"[style_gate] {verdict}：{len(files)} 个文件，违规 {len(issues)}" + (f" {counts}" if counts else ""))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
