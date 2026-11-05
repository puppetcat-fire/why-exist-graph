"""整个包共用的异常类型。

``Reject`` 表示可预期的拒绝：CLI 以非零退出并输出原因，不打印 traceback。
所有模块（含旧的入口脚本）都用同一个类，``except Reject`` 才能跨层生效。
"""

from __future__ import annotations

__all__ = ["Reject"]


class Reject(Exception):
    """可预期的拒绝：CLI 以非零退出并输出原因。"""
