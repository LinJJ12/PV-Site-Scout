"""把 backend/ 根目录加入 sys.path，供 ``python scripts/*.py`` 直接跑。"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_root = str(_BACKEND_ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)
