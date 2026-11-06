"""CLI 入口：argparse 构建与命令分派。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .contract import C
from .db import connect, db_backend, ensure_db
from .errors import Reject
from .jsonio import dumps

DEFAULT_ROOT = Path.cwd() / ".why-exist"

# ------------------------------------------------------------------ CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wxg", description="why-exist-graph：图库 / 工单 / 咬合 / 交付门")
    parser.add_argument("--root", default=None, help="状态库目录（默认 ./.why-exist）")
    parser.add_argument(
        "--db-url",
        default=None,
        help="状态库 URL，覆盖 WXG_DB_URL；mysql:// 走 MariaDB/MySQL，postgresql:// 走 PostgreSQL（需 psycopg）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, spec in C.COMMANDS.items():
        p = sub.add_parser(name, help=spec["help"], description=spec["help"])
        for pos in spec["positionals"]:
            p.add_argument(pos["name"], help=pos["help"], nargs=pos["nargs"] if pos["nargs"] else None)
        for opt in spec["options"]:
            p.add_argument(
                opt["flag"],
                dest=opt["dest"],
                required=opt["required"],
                default=opt["default"],
                choices=opt["choices"],
                type=opt["type"],
                help=opt["help"],
            )
        for flag in spec["flags"]:
            p.add_argument(flag["flag"], dest=flag["dest"], action="store_true", help=flag["help"])
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT.resolve()
    args.root_path = root
    if getattr(args, "db_url", None):
        os.environ["WXG_DB_URL"] = args.db_url
    try:
        backend = db_backend()
    except Reject as exc:
        print(dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    # 不需要状态库的命令不 connect：避免 verify/contract/role-prompt 在干净目录里
    # 创建 .why-exist/ 与空 graph.sqlite（这些命令必须是真只读、零副作用）。
    # up 例外：它要能在未初始化的目录里自建状态库，连接与提交由 cmd_up 自己管。
    needs_db = args.cmd not in ("verify", "contract", "role-prompt", "up")
    if needs_db and args.cmd != "init" and backend == "sqlite" and not (root / "graph.sqlite").is_file():
        # 状态库不存在时不再“先建空库再报错”，避免 gate/doctor 等命令留下 0 字节库。
        print(dumps({"error": "状态库未初始化：先运行 `wxg init`"}), file=sys.stderr)
        return 2
    # 命令处理器分散在 commands_* 模块，统一从入口模块 wxg 取（wxg 负责 re-export）。
    import wxg

    # 连接必须落在兜底之内：MySQL/PostgreSQL 的错密码、端口不通、没装 psycopg
    # 都会在 connect() 里抛异常。以前这行在 try 之外，四种失败全是裸 traceback +
    # 退出 1，直接违反「错误给可读 JSON、退出 2」的契约。
    conn = None
    try:
        if needs_db:
            conn = connect(root)
        if args.cmd == "init":
            result = wxg.cmd_init(conn, args)
            conn.commit()
        else:
            if needs_db:
                ensure_db(conn)
            handler = getattr(wxg, "cmd_" + args.cmd.replace("-", "_"))
            result = handler(conn, args)
            if needs_db:
                conn.commit()
    except Reject as exc:
        print(dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except Exception as exc:  # 后端/环境错误给可读 JSON，不把 traceback 当成功
        print(dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()
    if args.cmd in ("verify", "doctor"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "gate":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("result") == "PASS" else 1
    if args.cmd == "trace":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "apply":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "reconcile":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("converged") else 1
    if args.cmd == "serve":
        # cmd_serve 已经按趟打印 JSON；这里不再重复输出。
        return 0
    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


