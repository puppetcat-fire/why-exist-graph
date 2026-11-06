#!/usr/bin/env python3
"""wxg — why-exist-graph 的 DSH 原生实现（薄入口）。

实现在 ``whyexist`` 包里；这个文件只做三件事：

1. 准备 ``sys.path``；
2. 把 ``__main__`` 注册成 ``"wxg"``，让包内 ``import wxg`` 拿到同一模块对象
   （否则 ``Reject`` 会有两份，跨层 ``except Reject`` 捕获不到）；
3. 暴露 CLI 分派所需的 ``cmd_*`` 名字——``cli.py`` 与 ``verify`` 都是
   ``getattr(wxg, "cmd_" + name)`` 动态取，所以这些名字必须在这里可见。

其余包内符号不再 re-export。拆包时曾把 134 个名字整片搬过来，其中 76 个在仓内
没有任何消费者（AST 统计，排除本文件）；留着它们会让「这里到底发生了什么」变模糊。
现在只保留三类：CLI 处理器、``gen_sample.py`` 与测试 fixture 实际用到的 helper、
以及契约常量 ``C``（``gen_sample.py`` 通过 ``wxg.C`` 访问）。

CLI 本身在 ``whyexist.cli``。设计见 ``references/design.md``。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    sys.modules.setdefault("wxg", sys.modules["__main__"])

# gen_sample.py 通过 wxg.C 访问契约常量（唯一的外部消费者，其余模块直接 import 契约）
import wxg_contract as C  # noqa: E402,F401

# fixture 与测试仍在用的少量 helper：wxg.make_temp_dir / wxg.upsert_node / wxg.connect …
from whyexist.db import connect, init_db  # noqa: E402,F401
from whyexist.errors import Reject  # noqa: E402,F401
from whyexist.graph import bind_node, upsert_edge, upsert_node  # noqa: E402,F401
from whyexist.temp import make_temp_dir, temp_dir  # noqa: E402,F401

from whyexist.cli import main  # noqa: E402
from whyexist.commands_compiler import (  # noqa: E402
    cmd_apply,
    cmd_blind_check,
    cmd_brief,
    cmd_conflicts,
    cmd_cycles,
    cmd_impact,
    cmd_patch,
    cmd_plan,
)
from whyexist.commands_feature import (  # noqa: E402
    cmd_change_diff,
    cmd_change_open,
    cmd_feature_declare,
    cmd_feature_list,
    cmd_feature_register,
    cmd_feature_status,
    cmd_work_claim,
    cmd_work_finish,
    cmd_work_judge,
    cmd_work_list,
    cmd_work_open,
    cmd_work_seed,
)
from whyexist.commands_gates import (  # noqa: E402
    cmd_conformance,
    cmd_coverage,
    cmd_gate,
    cmd_reconcile,
    cmd_serve,
)
from whyexist.commands_graph import (  # noqa: E402
    cmd_bind,
    cmd_bite,
    cmd_bulk,
    cmd_evidence_list,
    cmd_evidence_record,
    cmd_retract,
    cmd_upsert_edge,
    cmd_upsert_node,
)
from whyexist.commands_misc import (  # noqa: E402
    cmd_contract,
    cmd_doctor,
    cmd_export,
    cmd_role_prompt,
    cmd_verify,
)
from whyexist.commands_repo import (  # noqa: E402
    cmd_derive,
    cmd_import_file,
    cmd_import_repo,
    cmd_init,
    cmd_promote,
    cmd_repo_add,
    cmd_repo_list,
    cmd_sample,
    cmd_sync,
    cmd_up,
)
from whyexist.commands_trace import (  # noqa: E402
    cmd_acceptance_add,
    cmd_acceptance_import,
    cmd_acceptance_status,
    cmd_requirement_scope,
    cmd_trace,
)
from whyexist.query import cmd_find, cmd_get, cmd_slice  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
