"""JSON 与基础工具：序列化、时间戳、令牌、``@文件`` 参数解析。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .errors import Reject

__all__ = ["dumps", "load_json_arg", "loads", "new_token", "utc_now"]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def loads(text, default):
    if text is None or text == "":
        return default
    if isinstance(text, (list, dict, int, float, bool)):
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise Reject(f"JSON 解析失败：{exc}") from exc


def load_json_arg(text: str):
    """解析 ``--data`` / ``--changed`` 一类参数：JSON 字面量或 ``@文件``。

    这两个入口同时接受"字符串"与"JSON"，只报 "JSON 解析失败" 太含糊——第一次用的
    人会以为参数本身写错了，而不是格式不对。报错里把期望格式和出错位置写出来。
    """
    if text.startswith("@"):
        path = Path(text[1:])
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise Reject(f"JSON 文件无法读取：{path}（{exc.strerror or exc}）") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise Reject(
                f"文件内容不是合法 JSON：{path}"
                f"（第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}）"
            ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise Reject(
            "参数不是合法 JSON：期望数组/对象字面量（如 '[\"id\"]'）或 @文件"
            f"（第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}）"
        ) from exc


def load_id_list(text: str) -> list[str]:
    """解析 id 列表参数：逗号分隔、JSON 数组或 ``@文件``。

    首字符是 ``[`` / ``"`` / ``{`` / ``@`` 时按 JSON 走（数组或文件），其余按逗号分隔。
    逗号写法是为了方便手敲；JSON 与 ``@文件`` 保留给脚本与长列表。
    """
    stripped = text.strip()
    if stripped[:1] in ("[", "@", '"', "{"):
        value = load_json_arg(stripped)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise Reject("id 列表必须是字符串数组（JSON 内联或 @文件）")
        return value
    return [item.strip() for item in stripped.split(",") if item.strip()]


def new_token() -> str:
    return uuid.uuid4().hex
