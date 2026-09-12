"""让 `pytest` 在仓库根把本仓库挂上 sys.path（测试里直接 import idiolect.*）。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
