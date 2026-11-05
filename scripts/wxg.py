#!/usr/bin/env python3
"""wxg — why-exist-graph 的 DSH 原生实现（薄入口）。

实现在 ``whyexist`` 包里；这个文件只做三件事：

1. 准备 ``sys.path``；
2. 把 ``__main__`` 注册成 ``"wxg"``，让包内 ``import wxg`` 拿到同一模块对象
   （否则 ``Reject`` 会有两份，跨层 ``except Reject`` 捕获不到）；
3. re-export 包内符号——旧测试仍按 ``wxg.xxx`` 访问。

CLI 本身在 ``whyexist.cli``。设计见 ``references/design.md``。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    sys.modules.setdefault("wxg", sys.modules["__main__"])

DEFAULT_ROOT = Path.cwd() / ".why-exist"

import wxg_contract as C  # noqa: E402

from whyexist.contract import DESIGN_ANCHOR_KINDS  # noqa: E402
from whyexist.db import (  # noqa: E402
    MYSQL_SCHEMA_SQL,
    PG_SCHEMA_SQL,
    SCHEMA_SQL,
    _MySQLConnection,
    _NoopCursor,
    _PgConnection,
    _is_integrity_error,
    _mysql_translate,
    _named_params,
    _pg_translate,
    _table_columns,
    connect,
    db_backend,
    db_url,
    ensure_db,
    init_db,
    migrate_schema,
)
from whyexist.errors import Reject  # noqa: E402
from whyexist.evidence import evidence_qualifies, sha256_file  # noqa: E402
from whyexist.gates import (  # noqa: E402
    _feature_bites,
    _required_coverage,
    _truncate,
    conformance_report,
    coverage_report,
    drift_report,
    reconcile_actions,
)
from whyexist.graph import (  # noqa: E402
    bind_node,
    check_attrs,
    check_kind,
    check_node_id,
    edge_id,
    find_repo,
    get_node,
    repo_rows,
    upsert_edge,
    upsert_node,
)
from whyexist.importer import _node_id, plan_python  # noqa: E402
from whyexist.jsonio import dumps, load_json_arg, loads, new_token, utc_now  # noqa: E402
from whyexist.query import (  # noqa: E402
    cmd_find,
    cmd_get,
    cmd_slice,
    resolve_targets,
    slice_payload,
)
from whyexist.temp import make_temp_dir, temp_dir  # noqa: E402
from whyexist.work import (  # noqa: E402
    append_evidence,
    get_work,
    get_work_by_token,
    insert_work,
    require_role,
    require_targets,
    require_token,
    target_match,
    work_id,
)
from whyexist.workflow import (  # noqa: E402
    actor_value,
    condition_flags,
    condition_rows,
    current_phase,
    ensure_feature,
    get_feature,
    recompute_ready,
    refresh_blocked,
    scope_ids,
    set_condition,
)

from whyexist.cli import build_parser, main  # noqa: E402
from whyexist.commands_compiler import (  # noqa: E402
    _brief_payload,
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
    _require_write,
    _resolve_subject,
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
    record_judge_history,
    work_seed,
)
from whyexist.commands_gates import (  # noqa: E402
    _pending_counts,
    apply_safe_actions,
    cmd_conformance,
    cmd_coverage,
    cmd_gate,
    cmd_reconcile,
    cmd_serve,
    reconcile_feature,
)
from whyexist.commands_graph import (  # noqa: E402
    cmd_bind,
    cmd_bite,
    cmd_evidence_list,
    cmd_evidence_record,
    cmd_retract,
    cmd_upsert_edge,
    cmd_upsert_node,
    prune_work_refs,
)
from whyexist.commands_misc import (  # noqa: E402
    cmd_contract,
    cmd_doctor,
    cmd_export,
    cmd_role_prompt,
    cmd_verify,
    doctor_report,
)
from whyexist.commands_repo import (  # noqa: E402
    _import_file_pairs,
    _module_to_rel,
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

if __name__ == "__main__":
    raise SystemExit(main())
