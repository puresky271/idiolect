"""爱音角色包数据：从 turn_logic 模块迁出的纯数据 JSON（2026-09 搬迁）。

只放数据、不放逻辑——cosmetics.json / fashion.json / social_media.json 由
对应 turn_logic 模块里的惰性加载器经 importlib.resources 读取；本文件存在
是为了让 data/ 成为常规子包（setuptools packages.find + package-data 需要）。
"""
