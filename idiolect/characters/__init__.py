"""五个示例角色包，按 key 分组：anon / tomori / taki / soyo / rana。

必须有这个文件：`pyproject.toml` 用 `namespaces = false` 打包，setuptools 只认带
`__init__.py` 的目录；缺了它 `find_packages(["idiolect*"])` 只返回 `idiolect` 一个包，
`pip install .` 装出来的 wheel 里就没有任何角色包（`python -m idiolect prompt` 会
以 `ModuleNotFoundError: No module named 'idiolect.characters'` 失败）。

调用方不要直接 import 这里的子包——只走 `idiolect/registry.py`。
"""
from __future__ import annotations
