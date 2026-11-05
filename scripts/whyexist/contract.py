"""桥接：why-exist 契约模块。

契约目前仍在 ``scripts/wxg_contract.py``——它被 ``verify``、测试与发布脚本直接引用。
等契约本身搬进包内，这个桥接就消失。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import wxg_contract as C  # noqa: E402

#: 可以锚定到代码（maps_to）的设计节点 kind。
DESIGN_ANCHOR_KINDS = ("use_case", "component", "port")

__all__ = ["C", "DESIGN_ANCHOR_KINDS"]
