"""临时目录工具。

Windows 上 Python >= 3.12.4 为了 CVE-2024-4030，把 ``os.mkdir(path, 0o700)`` 的目录
建造成只有创建者的显式 DACL；在 DSH 的 windows-acl 沙箱（受限 token）里该 DACL 解析
为空，目录创建者自己都写不进、删不掉（见 DSH discussion #4290）。这里在 Windows 上
改用默认 mode（继承父目录 ACL）建临时目录，POSIX 仍用 0o700。
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

__all__ = ["make_temp_dir", "temp_dir"]


def make_temp_dir(prefix: str = "wxg-") -> Path:
    base = Path(tempfile.gettempdir())
    for _ in range(100):
        path = base / (prefix + uuid.uuid4().hex)
        try:
            if os.name == "nt":
                path.mkdir()  # 默认 mode：继承可写 ACL，规避受限 token 下的空 DACL
            else:
                path.mkdir(mode=0o700)
        except FileExistsError:
            continue
        return path
    raise RuntimeError("无法创建临时目录")


@contextlib.contextmanager
def temp_dir(prefix: str = "wxg-"):
    path = make_temp_dir(prefix)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
