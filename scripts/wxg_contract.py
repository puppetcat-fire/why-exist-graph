"""wxg 契约层：why-exist-graph 的唯一真源。

这个模块只定义“系统是什么”，不碰数据库、不实现进程。运行时、文档、样例
全部从这里的常量生成或校验，因此不会出现“文档说一套、代码做一套”的漂移：

- CLI 子命令由 COMMANDS 生成；
- SKILL.md / references/contract.md 的契约块由本模块渲染；
- `wxg verify` 会重新渲染并与磁盘文件逐字节比较；
- 导出样例由同一套渲染器生成后再比较。

修改契约时改这一个文件，然后跑 `wxg contract --write ...` 与 `wxg verify`。
"""
from __future__ import annotations

import json

SCHEMA_VERSION = 9
CONTRACT_VERSION = "2.92.0"

#: ``doctor --fix`` 能自动修的检查项。其余问题（legacy 身份、条件行缺失、审计配对等）
#: 只能报给人看——要么需要裁决，要么需要改设计，自动修等于替人做决定。
DOCTOR_FIXABLE_CHECKS = (
    "dangling-bite",
    "orphan-edge",
    "feature-node-missing",
    "work-target-missing",
    "work-evidence-missing",
    "token-on-inactive",
    "meta-version",
)

# ---------------------------------------------------------------- 条件与工单

CONDITIONS = [
    "Accepted",
    "ArchitectureReconciled",
    "StructureReconciled",
    "InteractionsReconciled",
    "TestsSpecified",
    "TestsImplemented",
    "BehaviorPassed",
    "Ready",
]

# 条件 -> 由哪张工单通过后置真。Accepted 由声明命令置真；Ready 由判定命令派生。
CONDITION_TO_KIND = {
    "ArchitectureReconciled": "model-architecture",
    "StructureReconciled": "model-structure",
    "InteractionsReconciled": "interact",
    "TestsSpecified": "specify-test",
    "TestsImplemented": "implement-test",
    "BehaviorPassed": "observe",
}
KIND_TO_CONDITION = {kind: cond for cond, kind in CONDITION_TO_KIND.items()}

# 所有工单 kind。scan 与 audit 不由 work-seed 生成；audit 由 work-finish 生成。
WORK_KINDS = [
    "scan",
    "model-architecture",
    "model-structure",
    "interact",
    "specify-test",
    "implement-test",
    "observe",
    "audit",
]

# ---------------------------------------------------------------- 图结构

NODE_KINDS = [
    {"kind": "requirement", "desc": "功能声明；id 前缀 requirement:{feature}:", "creator": "声明入口"},
    {"kind": "actor", "desc": "角色", "creator": "model-architecture"},
    {"kind": "use_case", "desc": "用例；satisfies 指向 requirement", "creator": "model-architecture"},
    {"kind": "component", "desc": "构件；depends 指向 component", "creator": "model-architecture / scan 锚点"},
    {"kind": "port", "desc": "端口；associates 指向 component", "creator": "model-architecture / scan 锚点"},
    {"kind": "pattern", "desc": "设计模式实例；attrs 必须写 applicability/not_applicable，applies 挂到具体设计元素", "creator": "model-architecture / model-structure"},
    {"kind": "classifier", "desc": "类/接口/枚举等；contains 指向 operation 或 property", "creator": "scan / model-structure"},
    {"kind": "property", "desc": "字段/属性", "creator": "scan / model-structure"},
    {"kind": "operation", "desc": "函数/方法；calls、reads、writes", "creator": "scan / interact"},
    {"kind": "parameter", "desc": "入参/出参；通过 bind 挂到 operation", "creator": "interact / specify-test"},
    {"kind": "interaction", "desc": "交互；has_lifeline、has_message", "creator": "interact"},
    {"kind": "lifeline", "desc": "生命线", "creator": "interact"},
    {"kind": "message", "desc": "消息；has_argument", "creator": "interact"},
    {"kind": "argument", "desc": "消息参数；通过 bind 挂到 message", "creator": "interact"},
    {"kind": "sink", "desc": "数据落点（表/文件/外部系统）；operation writes 指向它", "creator": "interact / scan"},
    {"kind": "testcase", "desc": "测试用例；verifies 指向 use_case 或 operation", "creator": "specify-test"},
    {"kind": "assertion", "desc": "断言；asserts 指向已存在节点", "creator": "specify-test"},
]

EDGE_KINDS = [
    {"kind": "contains", "desc": "容器 -> 被包含节点"},
    {"kind": "satisfies", "desc": "use_case -> requirement"},
    {"kind": "verifies", "desc": "testcase -> use_case / operation"},
    {"kind": "include", "desc": "use_case -> use_case"},
    {"kind": "extend", "desc": "use_case -> use_case"},
    {"kind": "generalizes", "desc": "classifier -> classifier"},
    {"kind": "realizes", "desc": "classifier -> classifier"},
    {"kind": "associates", "desc": "任意节点 -> 任意节点"},
    {"kind": "maps_to", "desc": "设计节点（use_case/component/port）-> 代码节点（锚点，必须落在 repo/path 节点上）"},
    {"kind": "applies", "desc": "具体设计元素（component/classifier/operation）-> pattern（该元素采用该模式）"},
    {"kind": "depends", "desc": "component -> component"},
    {"kind": "calls", "desc": "operation -> operation"},
    {"kind": "reads", "desc": "operation -> property"},
    {"kind": "writes", "desc": "operation -> sink / property"},
    {"kind": "has_input", "desc": "operation -> parameter"},
    {"kind": "has_output", "desc": "operation -> parameter"},
    {"kind": "has_lifeline", "desc": "interaction -> lifeline"},
    {"kind": "has_message", "desc": "interaction -> message"},
    {"kind": "has_argument", "desc": "message -> argument"},
    {"kind": "asserts", "desc": "assertion -> 已存在节点"},
]

BIND_EDGE_KIND = {
    "parameter": "has_input",
    "argument": "has_argument",
    "assertion": "asserts",
}

# ---------------------------------------------------------------- 咬合

BITE_VERDICTS = ["KEEP", "UNNECESSARY", "HOLLOW", "DOC-ONLY", "UNMAPPED", "UNKNOWN"]
GATE_FAIL_VERDICTS = ["UNNECESSARY", "HOLLOW"]
# 结构性漂移判决：图与代码/文档对不上，但未必该删。--drift-limit 控制 gate 阈值。
DRIFT_VERDICTS = ["UNMAPPED", "DOC-ONLY"]

# 这些条件代表“行为已经跑过”；置真前必须有 exit_code=0 的 evidence 记录。
EVIDENCE_REQUIRED_CONDITIONS = ["BehaviorPassed"]

GATE_RULES = [
    "条件未齐（七项条件与 Ready 任一为假）→ FAIL。",
    "作用域内节点按**当前代最新一条** bite 计判决：最新为 UNNECESSARY/HOLLOW → FAIL；KEEP 只反证**同一节点**，跨节点或旧代 KEEP 不抵消。咬合只采信 `bites` 表（含 actor），`attrs.bite` 仅供展示。",
    "模式有限应用：作用域内每个 `pattern` 必须有非空 `applicability` 与 `not_applicable`，且至少被一条 `applies` 边挂到具体设计元素（component/classifier/operation），否则 FAIL。",
    "结构性漂移：feature 开启 `--drift-limit N` 时，作用域内当前代最新判决为 UNMAPPED/DOC-ONLY 的节点数超过 N 则 FAIL；未设置该策略只报告。",
    "施工中标记：`construction=true` 的节点（施工中代码段）在 gate 前必须清除，否则 FAIL；咬合逻辑不受标记影响。",
    "回扫生还：作用域内 `stale=1` 的节点（重扫时代码里已不存在的旧锚点）在 gate 前必须清除，否则 FAIL。",
    "设计-代码一致性：feature 开启 `--conformance` 时，gate 要求 use_case/component/port 有 `maps_to` 代码锚点、component/port 的 `depends` 有代码调用支撑、代码调用不出现未声明耦合、每个 use_case 至少被一个 testcase `verifies`；否则 FAIL。只报告检查结果，不生成新的设计描述。",
    "gate 只读：不写条件、不写工单、不改节点，重复执行结果不变；PASS 退出码 0、FAIL 退出码 1。",
    "除 Accepted 由 `feature-declare` / `feature-register` 新建时置真外，只有 work-judge(passed) 写条件；judge(failed) 把该条件及其后的条件置假，没有对应条件的工单（scan）不改条件。",
    "`BehaviorPassed` 置真前必须有一条**同 generation**、exit_code=0 且产物有效的 evidence（有产物时校验存在与 hash），gate 执行同样的检查。",
    "feature 开启 coverage 策略（默认对新 feature 开启；`--no-coverage` 关闭）时，gate 与 `work-judge(passed)` 都要求该阶段咬合覆盖达标；关闭则只报告不拦截。",
    "`retract` 会级联删除 bite；外部遗留的悬空 bite 不计入门禁（输出 ignored_dangling_bites），由 doctor 清理。",
]

AUDIT_RULES = [
    "`work-claim`、`work-judge`、`bite` 必须带 `--actor`（或 `WXG_ACTOR` 环境变量），记录到 `work_items.claimed_by` / `judged_by` / `bites.actor`。",
    "审计独立性：`work-judge --actor` 不得等于被审工单的 `claimed_by`；旧库迁移写入的 `legacy` 允许，但结果会带 `legacy_claim: true`，doctor 报 `legacy-identity`（不可追溯，不伪造成员）。",
    "`work-judge` 同时写 `judged_at`；一个工单的 `judged_by` 不允许被后续裁决覆盖（仅允许从空到有值）。",
    "`work-judge` 每次裁决（passed/failed）都写入 `judge_history`（裁决、理由、actor、时间，只增不删）；judge(passed) 同时清空该工单的陈旧 `fail_reason`。",
    "`attrs.bite` 只能由 `bite` 命令写入；`upsert-node` 等图写入不得写入 bite，gate 不采信图写入里的 bite 值。",
    "审计日志/证据不得只复述结论：至少记录执行者、命令、退出码或产物 hash，否则只能标 `UNKNOWN`/过程证据，不计入交付门。",
]

EVIDENCE_RULES = [
    "证据是状态库的一等记录：每次测试、HTTP 冒烟、gate、export、独立重跑用 `evidence-record` 写入 `evidence` 表。",
    "证据记录至少包含：feature、名称、命令、退出码、执行者、时间；有产物文件时同时写 artifact 路径与 SHA-256。",
    "`BehaviorPassed` 的裁决与 gate 都要求 feature 下**同 generation**、exit_code=0 的 evidence；有产物时还会校验产物存在/hash；没有有效证据时 judge 拒绝置真、gate 判 FAIL。",
    "`doctor` 校验 evidence 指向的产物仍存在且 hash 未变、退出码、generation 非空与 legacy 身份；重跑证据命令不得改写权威状态库与 export。",
    "`finalize`/一键重跑脚本必须幂等：默认 `--dry-run` 或默认不追加 bite；确需写状态时必须显式 `--apply`。",
]

# ---------------------------------------------------------------- 覆盖与调度

# feature 开启 --coverage-epsilon 后强制执行的默认参数。
COVERAGE_DEFAULTS = {"epsilon": 1.0, "prior_p": 0.1, "alpha": 2.0}

COVERAGE_RULES = [
    "覆盖对**新 feature 默认开启**（ε=1.0）；`feature-declare --no-coverage` 关闭，显式 `--coverage-epsilon` 覆盖默认值；重声明保留已有策略，旧库迁移后默认关闭。",
    "设作用域节点数 S、某阶段已覆盖节点数 n（同一节点多次咬合只算一次）、命中节点数 d（该节点任一判决非 KEEP 且非 UNKNOWN），后验缺陷率 p=(1+d)/(10+n)（Beta(1,9) 先验）。",
    "阶段推进前要求 p_m·(S-m) ≤ ε，其中 p_m=(1+d)/(10+m)（假设后续咬合不再新增命中）；n_required 取满足条件的最小 m，m 不超过 S（m=S 时残留期望为 0）。",
    "调度索引 I_i = α^(i-1)·p_i，α 默认 2，i 为条件在固定顺序中的位置；预算有限时优先把下一次咬合投给 I 最大的阶段；`coverage.next` 取**条件顺序里第一个未达标阶段**（阶段不能跳着推进）。",
    "`coverage` 只读输出各阶段的 bites、covered、hits、p、n_required、met 与调度建议；策略开启时 `work-judge(passed)` 与 `gate` 执行同一检查。",
]

JUDGE_HISTORY_COLUMNS = [
    ("id", "`jh:<uuid>`（迁移回填为 `jh:<work_item_id>`）"),
    ("work_item_id", "被裁决工单"),
    ("feature_id", "所属 feature"),
    ("generation", "所属 generation"),
    ("kind", "工单 kind"),
    ("verdict", "`passed` / `failed`"),
    ("reason", "失败理由，可空"),
    ("actor", "审计执行者 id"),
    ("judged_at", "UTC 时间"),
]

# ---------------------------------------------------------------- 调谐（reconcile）

RECONCILE_DEFAULTS = {"claim_ttl": 3600}

RECONCILE_RULES = [
    "reconcile 默认只读、幂等：同一状态重复运行输出相同；`converged`=gate PASS 且无待办动作，退出码 0，有待办 1，错误 2。",
    "自动迁移只限三类：补缺失工单、解 blocked、回收超过 `--claim-ttl` 的 claimed 工单（清 token/assignee/claimed_by 并回到 ready）。",
    "裁决、咬合、图写入、导出永不自动执行；覆盖缺口、漂移超限、施工标记、证据缺失只作为待办动作报告。",
    "`work_items.claimed_at` 由 `work-claim` 写入；旧库迁移时 claimed 行按 created_at 回填，无法还原真实领取时间。",
]

# ---------------------------------------------------------------- 变更集（change set）

CHANGE_RULES = [
    "`change-open` 只在 feature **Ready** 后使用：from-condition 之前的条件按上一代继承为真，从 from-condition 起重置为假，并开启新一代（generation+1）。",
    "被继承的条件在当前代没有审计单；`changes` 表记录 from/to generation 与 from-condition，doctor 核对继承来源。",
    "变更集会重新派工 from-condition 及其下游（含 implement-test、observe）；BehaviorPassed 必须用新代 evidence 重新证明，旧代证据不满足。",
    "`change-diff` 只读：比较当前代与上一代工单写过的节点集合（evidence_ids），输出 added/removed/kept、继承条件与待办条件、代码锚点。",
    "一个 feature 同时只允许一个未收口的变更集：变更代 Ready 之前再次 change-open 会被拒绝。",
]

# ---------------------------------------------------------------- 回扫断言

RESCAN_RULES = [
    "`sync --repo <id>` 只读：重新解析登记仓的 Python 文件，与 DB 图对比，输出 missing（DB 有、代码无）、new（代码有、DB 无）、changed（行号/名称变化）与 stale 计数。",
    "`import-file` 写入时，同 repo+path 下本次未再出现的旧节点标 `nodes.stale=1`（代码里已不存在）；再次导入出现则清 0。",
    "`--prepare` 会把该文件已有的旧节点 id 一并并入 scan 工单 target_ids，使 stale 标记不越出写入边界。",
    "gate 对作用域内 `stale=1` 的节点直接 FAIL；必须重扫/修正设计后清掉，不能带着已删除的代码锚点交付。",
    "sync 不写库；stale 清除只能通过 import-file 重扫或设计角色重写节点。",
]

# ---------------------------------------------------------------- 后端与常驻控制器

BACKEND_RULES = [
    "默认 SQLite（WAL + busy_timeout=5000）；设 `WXG_DB_URL=mysql://...` / `postgresql://...` 或全局 `--db-url` 切换后端。",
    "MySQL 后端使用内置的纯标准库客户端 `scripts/wxg_mysql.py`，不需要第三方包；PostgreSQL 后端需要 `pip install 'psycopg[binary]'`（未安装时连接报可读错误）。",
    "SQLite 仍是单写者；MariaDB/MySQL/PostgreSQL 允许不同行并发写，同一工单领取靠 `UPDATE ... WHERE status='ready'` 的原子 rowcount。",
    "同一个状态库不要混用后端；导出目录仍由 `--root` 决定，与 DB 后端无关。",
]

SERVE_RULES = [
    "`serve` 默认每 `--interval` 秒（默认 5）对全部 feature 跑一遍 reconcile，并打印一行 JSON 摘要。",
    "`--apply` 时只执行 reconcile 允许的三类安全迁移（补单/解阻塞/回收陈旧 claim）；裁决、咬合、图写入永不自动。",
    "`--once` 跑单趟后退出，便于测试与 CI；Ctrl+C 退出并保留已提交状态。",
    "常驻控制器与后端无关：SQLite 下是唯一写者，MySQL 下可多实例并行，但同一工单仍只有一个代理能领到。",
]

CONFORMANCE_RULES = [
    "`maps_to` 是设计节点到代码锚点的一条边，不复制代码结构；conformance 只输出差异（缺锚点、缺代码支撑、未声明耦合、缺测试覆盖、代码孤儿），不生成节点、不补写设计。",
    "锚点检查：use_case/component/port 至少要有一条 `maps_to` 指向带 repo/path 的代码节点；没有就列入 `anchors.missing`。",
    "结构检查：每条 component/port 的 `depends` 必须能在两边锚定的代码节点之间找到 calls/reads/writes 支撑；反向，代码调用跨了组件却没有 depends/associates，列入 `structural.undeclared`。",
    "跨文件裸名调用被导入器标成 unmapped 时，若名字在作用域内唯一，允许一次启发式解析用于“依赖是否有代码支撑”（计入 `structural.resolved_heuristically`）；不写回图，也不用于未声明耦合。",
    "代码反向：作用域内未被任何 `maps_to` 指向的 operation/classifier 列 `anchors.code_orphans`；只报告，不算 violation，也不要求每个操作都进设计图。",
    "测试覆盖：每个 use_case 至少要有一条来自 testcase 的 `verifies`；没有就列入 `tests.missing`（只在报告中，不替代 TestsSpecified 条件）。",
    "`maps_to` 写入时校验方向：src 必须是 use_case/component/port，dst 必须带 repo/path 的代码节点。",
    "feature 用 `--conformance` 开启 gate 强制；默认关闭，旧 feature 迁移后保持关闭。报告只读，写入由设计角色显式完成。",
]

# ---------------------------------------------------------------- 角色

ROLES = {
    "scan": ["import-file", "import-repo", "derive", "upsert-node", "retract", "get", "find", "slice", "work-finish", "role-prompt"],
    "model-architecture": ["derive", "promote", "upsert-node", "upsert-edge", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "model-structure": ["derive", "promote", "upsert-node", "upsert-edge", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "interact": ["upsert-node", "upsert-edge", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "specify-test": ["upsert-node", "upsert-edge", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "implement-test": ["upsert-node", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "observe": ["import-file", "import-repo", "derive", "upsert-node", "retract", "get", "find", "slice", "work-finish", "role-prompt"],
    "audit": ["get", "find", "slice", "work-judge", "role-prompt"],
}

# 证据登记是横切动作：每个角色都可以把测试/冒烟/重跑结果落成 evidence。
for _role in ROLES:
    ROLES[_role].append("evidence-record")

# 这些命令只在拿到 claim_token 后可执行（写图/提交）。
TOKEN_COMMANDS = ["upsert-node", "upsert-edge", "bind", "retract", "import-file", "work-finish"]

# implement-test 领取额外门槛：当轮明确允许改产品代码。
PRODUCT_CODE_ROLES = ["implement-test"]

# ---------------------------------------------------------------- 命令

def P(name, *, help="", nargs=None):
    return {"name": name, "help": help, "nargs": nargs}


def O(flag, *, dest=None, required=False, default=None, help="", choices=None, type=str):
    return {
        "flag": flag,
        "dest": dest or flag.lstrip("-").replace("-", "_"),
        "required": required,
        "default": default,
        "help": help,
        "choices": choices,
        "type": type,
    }


def F(flag, *, dest=None, help=""):
    return {"flag": flag, "dest": dest or flag.lstrip("-").replace("-", "_"), "action": "store_true", "help": help}


def C(help, positionals=None, options=None, flags=None, token=False):
    return {
        "help": help,
        "positionals": positionals or [],
        "options": options or [],
        "flags": flags or [],
        "token": token,
    }


COMMANDS = {
    "init": C("初始化状态库并做一次性旧库迁移；迁移后重复运行不改已有行"),
    "up": C(
        "一条命令立起工作区：init + demo 仓 + demo feature + 第一次 gate 结果（不自动裁决，幂等）",
        options=[
            O("--feature", default="demo", help="demo feature id，默认 demo"),
            O("--repo", default="demo", help="demo 仓 id，默认 demo"),
            O("--path", default=None, help="已有源码仓路径；省略则在工作区旁创建 demo 仓"),
            O(
                "--template",
                default="standard",
                choices=["minimal", "standard"],
                help="minimal 只建 feature；standard 另建 demo 仓与样例文件",
            ),
        ],
    ),
    "repo-add": C(
        "登记源码仓；技能里不写死任何仓名",
        options=[
            O("--id", required=True, help="仓 id，如 demo"),
            O("--path", required=True, help="源码仓路径（绝对，或相对当前工作目录）"),
            O("--language", default="python", choices=["python"], help="导入器语言（当前仅内置 python，见 design.md 边界）"),
        ],
    ),
    "repo-list": C("列出已登记仓"),
    "import-file": C(
        "按单个 Python 源码文件导入节点/边；--prepare 只预列 id 到 scan 工单（此时必须带 --feature）",
        options=[
            O("--file", required=True, help="源码文件路径（必须在已登记仓内）"),
            O("--feature", help="把导入节点登记进该 feature 作用域；--prepare 时必填"),
            O("--token", help="写库令牌（--prepare 时省略）"),
        ],
        flags=[F("--prepare", help="只预列，不写库")],
        token=True,
    ),
    "import-repo": C(
        "按仓批量导入全部 Python 文件；--prepare 只预列到 scan 工单",
        options=[
            O("--repo", required=True, help="已登记仓 id"),
            O("--feature", help="--prepare 时必填"),
            O("--token", help="写库令牌（--prepare 时省略）"),
        ],
        flags=[F("--prepare", help="只预列，不写库")],
        token=True,
    ),
    "derive": C(
        "从代码图推导 component/depends 候选（默认 dry-run；--apply 写入 origin=derived）",
        options=[
            O("--repo", required=True, help="已登记仓 id"),
            O("--feature", required=True, help="候选归属的 feature"),
            O("--depth", type=int, default=1, help="按几层目录分组，默认 1"),
            O(
                "--exclude",
                default=None,
                help="逗号分隔的目录前缀（如 tests,docs,extras），这些目录不参与分组",
            ),
            O("--token", default=None, help="--apply 时必须"),
        ],
        flags=[F("--apply", help="写入图库（origin=derived）")],
        token=True,
    ),
    "promote": C(
        "把 origin=derived 的候选节点提升为 declared，并记录裁决者（需 claim_token）",
        options=[
            O("--feature", required=True),
            O("--node", required=True, help="候选节点 id"),
            O("--actor", default=None, help="裁决者；也可用 WXG_ACTOR"),
            O("--token", default=None, help="写库令牌"),
        ],
        token=True,
    ),
    "sample": C(
        "从仓或 feature 作用域里随机取一个节点，作为撕咬入口",
        options=[
            O("--repo", default=None, help="按已登记仓抽样"),
            O("--feature", default=None, help="按 feature 作用域抽样（与 --repo 二选一）"),
            O("--seed", type=int, default=None),
        ],
    ),
    "feature-declare": C(
        "声明功能：generation+1，重置条件，只派 work-seed",
        options=[
            O("--id", required=True),
            O("--name", required=True),
            O("--statement", required=True),
            O("--acceptance", required=True, help="JSON 数组，或 @文件"),
            O("--constraints", required=True, help="JSON 数组，或 @文件"),
            O("--coverage-epsilon", type=float, default=None, help="覆盖门禁阈值（新 feature 默认 1.0）；与 --no-coverage 互斥"),
            O("--drift-limit", type=int, default=None, help="开启结构性漂移门禁：允许的 UNMAPPED/DOC-ONLY 节点数上限；省略则不强制"),
        ],
        flags=[
            F("--no-coverage", help="关闭新 feature 默认开启的覆盖门禁（与 --coverage-epsilon 互斥）"),
            F("--conformance", help="开启设计-代码一致性门禁（锚点/结构/测试覆盖差异）"),
            F("--no-conformance", help="关闭一致性门禁（与 --conformance 互斥）"),
        ],
    ),
    "feature-register": C(
        "登记已有图：同代登记不写条件；新建/新代只置 Accepted（--generation 会重置条件并 supersede 旧工单）",
        options=[
            O("--id", required=True),
            O("--name", required=True),
            O("--spec", required=True, help="JSON：statement/acceptance/constraints，或 @文件"),
            O("--generation", type=int, default=None, help="显式开新代（必须大于当前代；旧代工单会被 supersede）"),
        ],
    ),
    "feature-list": C("列出 feature 与当前 generation"),
    "feature-status": C("显示当前 generation 的条件、工单、咬合汇总", options=[O("--id", required=True)]),
    "change-open": C(
        "在 feature Ready 后开变更集：继承 from-condition 之前的条件，从它起重置并开启新一代，自动 seed 下游工单",
        options=[
            O("--feature", required=True),
            O("--id", default=None, help="变更集 id；省略为 ch-<新代>"),
            O("--statement", required=True, help="这次设计变更要解决什么"),
            O("--from-condition", dest="from_condition", required=True, choices=sorted(CONDITION_TO_KIND)),
        ],
    ),
    "change-diff": C(
        "只读对比：当前代与上一代工单写过的节点集合、继承/待办条件、代码锚点",
        options=[
            O("--feature", required=True),
            O("--from-generation", dest="from_generation", type=int, default=None, help="基线代；省略时取变更集的 from_generation 或当前代-1"),
        ],
    ),
    "work-open": C(
        "预开/扩展非 audit 工单的 target_ids（scan 与设计角色扩写入边界都用它）",
        options=[
            O("--feature", required=True),
            O("--kind", required=True, choices=WORK_KINDS),
            O("--target-ids", required=True, help="id 列表：逗号分隔、JSON 数组或 @文件"),
        ],
    ),
    "work-seed": C("按缺的条件各生成一张工单", options=[O("--feature", required=True)]),
    "work-claim": C(
        "按角色领取当前代一张 ready 工单，返回 claim_token 与切片（--brief 只给计数）",
        options=[
            O("--role", required=True, choices=sorted(ROLES)),
            O("--actor", default=None, help="领取者 id；也可用 WXG_ACTOR 环境变量"),
        ],
        flags=[
            F("--allow-product-code", help="implement-test 专用：当轮明确允许改产品代码"),
            F("--brief", help="不返回节点/边正文，只返回切片计数（大图省上下文）"),
        ],
    ),
    "work-finish": C("提交已领取工单；通过后生成 audit 工单", options=[O("--token", required=True)], token=True),
    "work-judge": C(
        "审计裁决一张 submitted 工单（仅 audit 角色）；BehaviorPassed 需要先登记 evidence",
        options=[
            O("--id", required=True, help="被审工单 id 或 audit 单 id"),
            O("--verdict", required=True, choices=["passed", "failed"]),
            O("--fail-reason", default=None),
            O("--role", default="audit", choices=sorted(ROLES)),
            O("--actor", default=None, help="审计执行者 id；不得等于被审工单的 claimed_by"),
        ],
    ),
    "work-list": C("列出某 feature 当前 generation 的工单", options=[O("--feature", required=True)]),
    "upsert-node": C("写节点；id 已存在则更新（不接受 attrs.bite）", options=[O("--token", required=True), O("--data", required=True, help="JSON 或 @文件")], token=True),
    "upsert-edge": C("写边；两端必须已存在", options=[O("--token", required=True), O("--data", required=True, help="JSON 或 @文件")], token=True),
    "bind": C(
        "绑定 parameter/argument/assertion 到已存在节点",
        options=[
            O("--token", required=True),
            O("--node-id", required=True),
            O("--bind-to", required=True),
            O("--edge-kind", default=None, choices=sorted(set(BIND_EDGE_KIND.values()))),
        ],
        token=True,
    ),
    "retract": C(
        "撤回 target_ids 内的节点与边；级联删除 bite 并剔除工单引用",
        options=[O("--token", required=True), O("--node-ids", default=None, help="id 列表：逗号分隔、JSON 数组或 @文件"), O("--edge-ids", default=None, help="id 列表：逗号分隔、JSON 数组或 @文件")],
        token=True,
    ),
    "bite": C(
        "记录一次必要性判定；判决集固定，写 bites 与节点 attrs.bite（唯一写入口）",
        options=[
            O("--node", required=True),
            O("--verdict", required=True, choices=BITE_VERDICTS),
            O("--reason", default=""),
            O("--feature", default=None, help="同时登记为 feature 作用域内的咬合"),
            O("--actor", default=None, help="撕咬执行者 id；也可用 WXG_ACTOR 环境变量"),
        ],
    ),
    "evidence-record": C(
        "记录一条可追溯证据：命令、退出码、执行者、产物 hash（BehaviorPassed 的门槛）",
        options=[
            O("--feature", required=True),
            O("--name", required=True, help="证据名称，如 unittest-gen2 / http-smoke"),
            O("--command", required=True, help="复现命令原文"),
            O("--exit-code", dest="exit_code", type=int, default=0),
            O("--artifact", default=None, help="产物文件路径；存在时计算 SHA-256"),
            O("--work", default=None, help="可选：关联工单 id"),
            O("--actor", default=None, help="执行者 id；也可用 WXG_ACTOR 环境变量"),
        ],
    ),
    "evidence-list": C("列出某 feature 的证据记录", options=[O("--feature", required=True)]),
    "coverage": C(
        "按咬合覆盖公式计算各阶段 n/d/p/n_required 与调度索引（只读）",
        options=[
            O("--feature", required=True),
            O("--epsilon", type=float, default=None, help="覆盖阈值；省略时用 feature 策略，再缺省用契约默认 1.0"),
            O("--prior-p", dest="prior_p", type=float, default=None, help="缺陷率先验均值（Beta 先验），默认 0.1"),
        ],
        flags=[F("--json")],
    ),
    "reconcile": C(
        "控制器单步：对比期望与观测并输出待办动作；--apply 只做安全迁移（补单/解阻塞/回收陈旧 claim），不裁决不咬合不写图",
        options=[
            O("--feature", required=True),
            O("--claim-ttl", dest="claim_ttl", type=int, default=None, help="claim 超时秒数，默认 3600"),
        ],
        flags=[F("--apply", help="执行安全迁移；默认只读")],
    ),
    "serve": C(
        "常驻控制器：周期性对全部 feature 跑 reconcile 安全迁移；--once 单趟便于测试",
        options=[
            O("--interval", type=int, default=5, help="两趟之间的秒数，默认 5"),
            O("--feature", default=None, help="只跑某个 feature；省略为全部"),
            O("--claim-ttl", dest="claim_ttl", type=int, default=None, help="claim 超时秒数，默认 3600"),
        ],
        flags=[F("--once", help="只跑一趟后退出"), F("--apply", help="执行安全迁移；默认只读")],
    ),
    "sync": C(
        "只读回扫断言：重新解析登记仓，对比 DB 图与当前代码，报 missing/new/changed/stale",
        options=[
            O("--repo", required=True),
            O("--limit", type=int, default=50, help="每个列表最多返回多少条，默认 50"),
        ],
    ),
    "plan": C(
        "并行规划：从 feature 依赖图算强连通分量、调度波次、最大反链与理论并行上限（只读；默认排除 unmapped 噪声）",
        options=[
            O("--feature", required=True),
            O(
                "--level",
                default="auto",
                choices=["auto", "design", "code"],
                help="依赖图层级：design=depends / code=calls,reads,writes / auto 优先 design，无设计边时退到 code",
            ),
        ],
        flags=[
            F(
                "--include-unmapped",
                help="把 unmapped 节点也纳入统计；默认排除，避免内置调用噪声把并行度顶到假值",
            ),
        ],
    ),
    "cycles": C(
        "依赖环分析：把 design 层的强连通分量展开成具体依赖边与文件证据（只读）",
        options=[
            O("--feature", required=True),
            O(
                "--without",
                default=None,
                help="what-if：逗号分隔的 src->dst，模拟移除这些依赖后还剩哪些环",
            ),
        ],
        flags=[
            F("--break-set", help="枚举能破环的最小依赖边集合（边数不超过 20 才枚举）"),
            F(
                "--advise",
                help="对环内每条边给出断边建议：是否在最小断边集合里 + 断了丢多少可达",
            ),
        ],
    ),
    "brief": C(
        "生成一张工单的盲化任务书：只含写入边界、输入契约、产出契约与完成定义（只读）",
        options=[
            O("--work", required=True, help="工单 id"),
            O("--out", default=None, help="写到文件；省略则打印 JSON"),
        ],
    ),
    "blind-check": C(
        "盲执行校验：拿任务书与独立执行者的产出，检查写入边界、产出契约与依赖引用（只读）",
        options=[
            O("--work", required=True, help="工单 id"),
            O("--result", required=True, help="执行者产出 JSON 文件（nodes / edges）"),
        ],
    ),
    "patch": C(
        "把一次盲执行产出规范成补丁文件（只读；--out 写文件），供 apply 合并",
        options=[
            O("--work", required=True, help="工单 id"),
            O("--result", required=True, help="执行者产出 JSON 文件"),
            O("--out", required=True, help="补丁输出路径"),
        ],
    ),
    "apply": C(
        "合并补丁并写入图库：冲突显式报告且不写半截；--dry-run 只报告",
        options=[
            O("--patches", required=True, help="补丁文件列表，逗号分隔"),
        ],
        flags=[F("--dry-run", help="只合并与校验，不写库")],
    ),
    "impact": C(
        "影响域闭包：改动节点的下游可达集与需求覆盖，或断掉依赖边后的失去可达（只读）",
        options=[
            O("--feature", required=True),
            O(
                "--changed",
                default=None,
                help="被改动节点 id：逗号分隔、JSON 数组或 @文件；与 --remove-edges 二选一",
            ),
            O(
                "--remove-edges",
                dest="remove_edges",
                default=None,
                help="逗号分隔的 src->dst，分析断掉这些依赖后源点失去哪些可达节点",
            ),
        ],
    ),
    "conflicts": C(
        "声明期冲突检测：列出 feature 之间会重叠的 target_ids 写边界（只读）",
        options=[
            O("--features", default=None, help="逗号分隔的 feature id；省略则检查全部"),
        ],
    ),
    "conformance": C(
        "只读一致性检查：设计锚点、depends 的代码支撑、未声明耦合、use_case 的测试覆盖；只报差异",
        options=[
            O("--feature", required=True),
            O("--limit", type=int, default=50, help="每个列表最多返回多少条，默认 50"),
        ],
    ),
    "gate": C("交付门：只读计算 PASS/FAIL；PASS 退出码 0、FAIL 退出码 1", options=[O("--feature", required=True)], flags=[F("--json")]),
    "export": C("按 feature 导出六份只读视图（写入 <root>/export/）", options=[O("--feature", required=True)]),
    "slice": C("取工单或 target_ids 的深度 1 切片（只读；target_ids 支持 `前缀*` 与 @文件；--limit 防大图刷屏）", options=[O("--work", default=None), O("--ids", default=None, help="id 列表：逗号分隔、JSON 数组或 @文件"), O("--limit", type=int, default=None, help="最多返回多少节点/边")]),
    "get": C("按 id 读取一个节点", options=[O("--id", required=True)]),
    "find": C("按 kind / 路径前缀 / 入边起点查找节点（--limit 防大图刷屏）", options=[O("--kind", default=None, choices=[k["kind"] for k in NODE_KINDS]), O("--path-prefix", default=None), O("--from-id", default=None), O("--limit", type=int, default=None)]),
    "role-prompt": C(
        "生成可交给 DSH teammate 的角色提示（含状态库路径、允许命令与边界）",
        options=[O("--role", required=True, choices=sorted(ROLES)), O("--token", default=None), O("--feature", default=None)],
    ),
    "contract": C("输出契约；--write 刷新文档契约块", options=[O("--write", default=None), O("--section", default="main", choices=["main", "full"])], flags=[F("--json")]),
    "verify": C("一致性自检：契约块、角色/命令/kind 交叉引用、导出样例、写入列；不替代 doctor/行为测试"),
    "doctor": C(
        "状态库自检：悬空 bite/边/引用、陈旧 token、条件与审计配对、legacy 身份、证据产物；--fix 只清理悬空引用与陈旧 token",
        flags=[F("--fix", help="删除悬空引用并清空非 claimed 工单的陈旧 token")],
    ),
}

# 命令表“写入”列的唯一来源：显式声明，避免再靠 help 文本猜。
WRITE_MODES = {
    "init": "状态库（首次迁移）",
    "up": "状态库 / 文件（demo 仓）",
    "repo-add": "状态库",
    "repo-list": "只读",
    "import-file": "写图需 claim_token；--prepare 免 token",
    "import-repo": "写图需 claim_token；--prepare 免 token",
    "derive": "只读（--apply 时写图，需 claim_token）",
    "promote": "需要 claim_token / 角色命令",
    "sample": "只读",
    "feature-declare": "状态库",
    "feature-register": "状态库",
    "feature-list": "只读",
    "feature-status": "只读",
    "change-open": "状态库",
    "change-diff": "只读",
    "work-open": "状态库",
    "work-seed": "状态库",
    "work-claim": "状态库",
    "work-finish": "需要 claim_token / 角色命令",
    "work-judge": "状态库",
    "work-list": "只读",
    "upsert-node": "需要 claim_token / 角色命令",
    "upsert-edge": "需要 claim_token / 角色命令",
    "bind": "需要 claim_token / 角色命令",
    "retract": "需要 claim_token / 角色命令",
    "bite": "状态库",
    "evidence-record": "状态库",
    "evidence-list": "只读",
    "coverage": "只读",
    "reconcile": "只读（--apply 时状态库）",
    "serve": "只读（--apply 时状态库）",
    "sync": "只读",
    "plan": "只读",
    "cycles": "只读",
    "brief": "只读（--out 时写文件）",
    "blind-check": "只读",
    "patch": "只读（--out 时写文件）",
    "apply": "状态库（全量校验通过才写）",
    "impact": "只读",
    "conflicts": "只读",
    "conformance": "只读",
    "gate": "只读",
    "export": "文件（<root>/export/）",
    "slice": "只读",
    "get": "只读",
    "find": "只读",
    "role-prompt": "只读",
    "contract": "只读（--write 时写文档）",
    "verify": "只读",
    "doctor": "只读（--fix 时状态库）",
}

# ---------------------------------------------------------------- 属性契约

ATTR_SCHEMA = {
    "requirement": {"statement": "str"},
    "actor": {},
    "use_case": {"goal": "str", "actor": "str"},
    "component": {"duty": "str", "construction": "bool"},
    "port": {"port": "int", "protocol": "str"},
    "pattern": {
        "intent": "str",
        "applicability": "str",
        "not_applicable": "str",
        "forces": "str",
        "cost": "str",
        "alternative": "str",
        "source": "str",
    },
    "classifier": {"duty": "str", "construction": "bool"},
    "property": {"column": "str"},
    "operation": {"http": "str", "success_code": "str", "async": "bool", "construction": "bool"},
    "parameter": {"column": "str", "on_insert": "str", "note": "str", "example": "任意"},
    "interaction": {},
    "lifeline": {},
    "message": {},
    "argument": {},
    "sink": {"table": "str", "store": "str"},
    "testcase": {"path": "str", "text": "str", "layer": "str"},
    "assertion": {"text": "str", "success_code": "str", "column": "str"},
}

COMMON_ATTRS = {
    "bite": "str，取值见咬合判决；只读，由 `bite` 命令写入（图写入命令不允许写该键）",
    "x_*": "任意，项目自定义扩展键",
}

# ---------------------------------------------------------------- 导出

EXPORT_FILES = [
    {"name": "01-需求.md", "title": "01 需求", "columns": ["id", "能力", "验收", "约束"]},
    {"name": "02-用例.md", "title": "02 用例", "columns": ["id", "名称"]},
    {"name": "04-架构.md", "title": "04 架构", "columns": ["kind", "id", "名称"]},
    {"name": "05-类图.md", "title": "05 类图", "columns": ["kind", "名称", "路径", "符号", "unmapped"]},
    {
        "name": "07-数据流.md",
        "title": "07 数据流",
        "columns": ["步", "操作", "符号", "写入", "断言"],
        "extra_sections": [{"title": "请求参数", "columns": ["参数", "unmapped", "属性"]}],
    },
    {"name": "测试规格.md", "title": "测试规格", "columns": ["kind", "id", "名称", "属性"]},
]

EXPORT_RULE = (
    "导出只包含图里连到该 feature 的记录：01 取 requirement；02 取 satisfies 这些 requirement 的 use_case；"
    "04 取用例经 depends/associates/realizes 到达的 component 与 port，以及 feature 作用域内的 pattern；05 取用例 contains 的 operation 及其 has_input、"
    "以及 contains 指向这些 operation 的 classifier；07 每条 writes->sink 算一步，另附请求参数表（同一参数只列一次，顺序按首次出现）；"
    "测试规格取 verifies 到这些 operation/use_case 的 testcase 与 asserts 到 operation 的 assertion。"
    "缺的格子留空，禁止从任何旧文档补句。参数、测试与断言按 id 去重。"
)

# ---------------------------------------------------------------- 不变量

INVARIANTS = [
    ("I1 单一契约", "条件、工单、角色、命令、属性键、导出形状（含 07 的附加表与命令“写入”列）在 wxg_contract.py 定义；CLI 与生成文档块由它生成，`wxg verify` 校验生成视图与导出样例的字节一致性（不校验手写正文语义）。"),
    ("I2 generation 是身份", "条件与工单 id 都带 generation；重新声明会开启新一代并 supersede 旧工单，work-claim 只发当前代；不会出现旧 passed 工单挡住或混淆新条件。"),
    ("I3 交付门只读", "gate 不写库；正常流程中条件只由 work-judge(passed) 改写，Accepted 由声明/登记入口新建时置真。判定与状态变更分离。"),
    ("I4 判决可校验", "bite 是唯一写入咬合的命令，只接受固定判决集；gate 只采信 bites 表，作用域包含 feature_nodes、requirement 前缀与当前代工单 target_ids。"),
    ("I5 写入有边界", "图内容写入（upsert-node/upsert-edge/bind/retract/import-file）必须带 claim_token 且落在工单 target_ids 内；角色只能调用自己在 ROLES 里的命令。feature-declare / feature-register 只写 feature 元数据与 requirement 节点，bite 只写 bites/attrs.bite 且必须带 actor。"),
    ("I6 技能通用", "技能不写死仓名、工作区路径；仓在运行期 repo-add 登记，状态库路径用 --root 指定；导入器当前仅 Python AST（扩展边界见 design.md）。"),
    ("I7 不臆造", "认不出的节点/边标 unmapped=1；导出缺 id 留空；BehaviorPassed 置真前必须有**同 generation**、exit_code=0 的 evidence，judge 与 gate 双向强制。"),
    ("I8 文档即生成的视图", "SKILL.md 与 references/contract.md 的契约块、references/export-sample 的样例都由同一实现生成；verify 比较字节。"),
    ("I9 状态可自检", "doctor 检查悬空 bite/边/引用、陈旧 token、条件完整性、审计配对、legacy 身份与证据产物；--fix 只自动修可判定问题（dangling-bite / orphan-edge / feature-node-missing / work-target-missing / work-evidence-missing / token-on-inactive / meta-version），其余只报不修，不替人裁决。"),
    ("I10 审计可追溯", "work-claim / work-judge / bite 记录 actor；审计 actor 不得等于被审工单的 claimed_by；judged_by/judged_at 只写一次；gate 采信的咬合以 bites 表为准。"),
    ("I11 证据可追溯", "evidence-record 把命令、退出码、generation、执行者、产物 SHA-256 写入 evidence 表；doctor 校验产物存在/hash/退出码/generation 非空与 legacy 身份；judge/gate 对 BehaviorPassed 强制同代、exit_code=0 且产物有效的 evidence；重跑证据不得改写权威状态。"),
    ("I12 模式有限应用", "pattern 是设计决策节点：必须写 applicability 与 not_applicable，必须被 applies 挂到具体设计元素；gate 强制，误用/过度应用由 UNNECESSARY/DOC-ONLY 咬合反证。"),
    ("I13 判决按最新", "gate 采信当前代每个节点的最新 bite；最新为 UNNECESSARY/HOLLOW 即 FAIL；KEEP 只反证同一节点，跨节点、旧代 KEEP 不抵消。"),
    ("I14 失败历史", "每次 work-judge 写 judge_history（只增不删）；judge(passed) 清空陈旧 fail_reason；doctor 校验裁决历史与工单的关联与 actor。"),
    ("I15 覆盖可计算", "coverage 公式与默认参数（ε=1.0、先验 p=0.1、α=2）由契约定义；新 feature 默认开启 coverage，`--no-coverage` 关闭；work-judge(passed) 与 gate 要求该阶段覆盖达标。"),
    ("I16 漂移可门禁", "feature 开启 --drift-limit 后，gate 统计当前代最新判决为 UNMAPPED/DOC-ONLY 的节点数，超限即 FAIL；未开启只报告不拦截。"),
    ("I17 调谐可重复", "reconcile 默认只读且幂等；--apply 只做补单/解阻塞/回收陈旧 claim，不裁决、不咬合、不写图；交付判定仍由 gate 给出。"),
    ("I18 变更可追溯", "change-open 只在 Ready 后开启新代，并按 from-condition 继承上游条件；changes 表记录 from/to generation 与继承边界，change-diff 只读对比两代写过的节点集合，旧代 evidence 不满足新代 BehaviorPassed。"),
    ("I19 回扫可断言", "sync 只读对比 DB 图与当前 AST；import-file 把本次未再出现的旧节点标 stale=1，gate 对作用域内 stale 节点 FAIL；stale 只能由重扫或设计重写清除。"),
    ("I20 控制器可常驻", "serve 周期跑 reconcile；--apply 只做补单/解阻塞/回收陈旧 claim；--once 单趟；控制器可接 SQLite 或 MySQL，裁决/咬合永不自动。"),
    ("I21 一致性只报差异", "conformance 只做差异检查：设计节点的 maps_to 锚点、depends 的代码支撑、未声明耦合、use_case 的测试覆盖；不生成节点、不补写设计，开关由 feature 的 --conformance 决定。"),
]

# ---------------------------------------------------------------- 渲染

_MAIN_BEGIN = "<!-- wxg:contract:main:begin -->"
_MAIN_END = "<!-- wxg:contract:main:end -->"
_FULL_BEGIN = "<!-- wxg:contract:full:begin -->"
_FULL_END = "<!-- wxg:contract:full:end -->"


def _cmd_params(spec) -> str:
    parts = [p["name"] for p in spec["positionals"]]
    for opt in spec["options"]:
        if opt["required"]:
            parts.append(opt["flag"] + " <值>")
    for flag in spec["flags"]:
        if flag["action"] == "store_true":
            parts.append(flag["flag"])
    return " ".join(parts) if parts else "—"


def _cmd_write(name: str) -> str:
    return WRITE_MODES.get(name, "状态库" if name in COMMANDS and COMMANDS[name]["token"] else "只读")


def main_contract_markdown() -> str:
    lines = []
    lines.append("### 条件顺序（8 项，固定）")
    lines.append("")
    lines.append("| 条件 | 置真方式 |")
    lines.append("|------|----------|")
    for cond in CONDITIONS:
        if cond == "Accepted":
            how = "`feature-declare` 置真；`feature-register` 仅新建/新代时置真"
        elif cond == "Ready":
            how = "前七项全真时由 `work-judge(passed)` 派生；没有自己的工单"
        else:
            how = f"`{CONDITION_TO_KIND[cond]}` 工单 judged passed"
        lines.append(f"| `{cond}` | {how} |")
    lines.append("")
    lines.append("### 角色与允许命令")
    lines.append("")
    lines.append("| 角色 | 允许命令 |")
    lines.append("|------|----------|")
    for role in ROLES:
        lines.append(f"| `{role}` | " + "、".join(f"`{c}`" for c in ROLES[role]) + " |")
    lines.append("")
    lines.append("### 命令")
    lines.append("")
    lines.append("| 命令 | 用途 | 关键参数 | 写入 |")
    lines.append("|------|------|----------|------|")
    for name, spec in COMMANDS.items():
        lines.append(f"| `{name}` | {spec['help']} | {_cmd_params(spec)} | {_cmd_write(name)} |")
    lines.append("")
    lines.append("### 咬合判决")
    lines.append("")
    lines.append("允许值：" + "、".join(f"`{v}`" for v in BITE_VERDICTS) + "。")
    lines.append("")
    lines.append("结构性漂移判决：" + "、".join(f"`{v}`" for v in DRIFT_VERDICTS) + "（由 `--drift-limit` 控制是否拦门）。")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in GATE_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 咬合覆盖与调度（feature 显式开启后强制）")
    lines.append("")
    lines.append("默认参数：" + "，".join(f"`{key}={value}`" for key, value in COVERAGE_DEFAULTS.items()) + "。")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in COVERAGE_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 调谐（reconcile）")
    lines.append("")
    lines.append("默认参数：" + "，".join(f"`{key}={value}`" for key, value in RECONCILE_DEFAULTS.items()) + "。")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in RECONCILE_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 变更集（change set）")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in CHANGE_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 回扫断言（rescan）")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in RESCAN_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 设计-代码一致性（conformance）")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in CONFORMANCE_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 状态库后端")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in BACKEND_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 常驻控制器（serve）")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in SERVE_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 审计与证据")
    lines.append("")
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in AUDIT_RULES + EVIDENCE_RULES:
        lines.append(f"| {rule} |")
    lines.append("")
    lines.append("### 导出文件")
    lines.append("")
    lines.append("| 文件 | 列 |")
    lines.append("|------|----|")
    for entry in EXPORT_FILES:
        lines.append(f"| `{entry['name']}` | " + "、".join(entry["columns"]) + " |")
    for entry in EXPORT_FILES:
        for section in entry.get("extra_sections", []):
            lines.append("")
            lines.append(
                f"`{entry['name']}` 另含小节 `{section['title']}`，列：" + "、".join(section["columns"]) + "。"
            )
    lines.append("")
    lines.append("### 一致性不变量")
    lines.append("")
    lines.append("| 编号 | 不变量 |")
    lines.append("|------|--------|")
    for name, text in INVARIANTS:
        lines.append(f"| {name} | {text} |")
    lines.append("")
    return "\n".join(lines)


def full_contract_markdown() -> str:
    lines = [main_contract_markdown()]
    lines.append("### 节点 kind")
    lines.append("")
    lines.append("| kind | 说明 | 创建者 |")
    lines.append("|------|------|--------|")
    for entry in NODE_KINDS:
        lines.append(f"| `{entry['kind']}` | {entry['desc']} | {entry['creator']} |")
    lines.append("")
    lines.append("### 边 kind")
    lines.append("")
    lines.append("| kind | 说明 |")
    lines.append("|------|------|")
    for entry in EDGE_KINDS:
        lines.append(f"| `{entry['kind']}` | {entry['desc']} |")
    lines.append("")
    lines.append("### 属性键（attrs_json）")
    lines.append("")
    lines.append("公共键：`bite`（只读，仅由 `bite` 命令写入）、`x_*`。其余按节点 kind：")
    lines.append("")
    lines.append("| kind | 允许键 |")
    lines.append("|------|--------|")
    for kind in [entry["kind"] for entry in NODE_KINDS]:
        keys = ATTR_SCHEMA.get(kind, {})
        text = "、".join(f"`{k}`:{v}" for k, v in keys.items()) if keys else "—"
        lines.append(f"| `{kind}` | {text} |")
    lines.append("")
    lines.append("### 证据记录（evidence）")
    lines.append("")
    lines.append("| 列 | 含义 |")
    lines.append("|----|------|")
    for column, desc in (
        ("id", "`ev:<uuid>`"),
        ("feature_id", "所属 feature"),
        ("generation", "证据所属 generation（BehaviorPassed 只认同代证据）"),
        ("work_item_id", "可选关联工单"),
        ("name", "证据名称"),
        ("command", "复现命令原文"),
        ("exit_code", "命令退出码"),
        ("artifact_path", "产物文件路径，可空"),
        ("artifact_sha256", "产物 SHA-256，可空"),
        ("actor", "执行者 id"),
        ("created_at", "UTC 时间"),
    ):
        lines.append(f"| `{column}` | {desc} |")
    lines.append("")
    lines.append("### 裁决历史（judge_history）")
    lines.append("")
    lines.append("| 列 | 含义 |")
    lines.append("|----|------|")
    for column, desc in JUDGE_HISTORY_COLUMNS:
        lines.append(f"| `{column}` | {desc} |")
    lines.append("")
    lines.append("### 导出规则")
    lines.append("")
    lines.append(EXPORT_RULE)
    lines.append("")
    lines.append(f"契约版本 `{CONTRACT_VERSION}`，库 schema 版本 `{SCHEMA_VERSION}`。")
    lines.append("")
    return "\n".join(lines)


def _jsonable(value):
    """把 argparse 的 type=... 类对象转成名字，保证 contract --json 可序列化。"""
    if isinstance(value, type):
        return value.__name__
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def contract_json() -> dict:
    return _jsonable({
        "version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "conditions": CONDITIONS,
        "condition_to_kind": CONDITION_TO_KIND,
        "work_kinds": WORK_KINDS,
        "node_kinds": NODE_KINDS,
        "edge_kinds": EDGE_KINDS,
        "roles": ROLES,
        "commands": COMMANDS,
        "attr_schema": ATTR_SCHEMA,
        "common_attrs": COMMON_ATTRS,
        "bite_verdicts": BITE_VERDICTS,
        "gate_fail_verdicts": GATE_FAIL_VERDICTS,
        "drift_verdicts": DRIFT_VERDICTS,
        "evidence_required_conditions": EVIDENCE_REQUIRED_CONDITIONS,
        "gate_rules": GATE_RULES,
        "coverage_defaults": COVERAGE_DEFAULTS,
        "coverage_rules": COVERAGE_RULES,
        "reconcile_defaults": RECONCILE_DEFAULTS,
        "reconcile_rules": RECONCILE_RULES,
        "change_rules": CHANGE_RULES,
        "rescan_rules": RESCAN_RULES,
        "backend_rules": BACKEND_RULES,
        "serve_rules": SERVE_RULES,
        "conformance_rules": CONFORMANCE_RULES,
        "judge_history_columns": [{"column": column, "desc": desc} for column, desc in JUDGE_HISTORY_COLUMNS],
        "audit_rules": AUDIT_RULES,
        "evidence_rules": EVIDENCE_RULES,
        "command_write_modes": WRITE_MODES,
        "export_files": EXPORT_FILES,
        "export_rule": EXPORT_RULE,
        "invariants": [{"name": n, "text": t} for n, t in INVARIANTS],
    })


_BLOCKS = {
    "main": (_MAIN_BEGIN, _MAIN_END, main_contract_markdown),
    "full": (_FULL_BEGIN, _FULL_END, full_contract_markdown),
}


def replace_block(text: str, section: str, body: str | None = None) -> str:
    begin, end, renderer = _BLOCKS[section]
    body = body if body is not None else renderer()
    if begin not in text or end not in text:
        raise ValueError(f"文件里找不到契约块标记：{section}")
    head, rest = text.split(begin, 1)
    _old, tail = rest.split(end, 1)
    return f"{head}{begin}\n{body.rstrip()}\n{end}{tail}"


def extract_block(text: str, section: str) -> str:
    begin, end, _renderer = _BLOCKS[section]
    if begin not in text or end not in text:
        raise ValueError(f"文件里找不到契约块标记：{section}")
    return text.split(begin, 1)[1].split(end, 1)[0].strip("\n")


def contract_version_line() -> str:
    return f"wxg contract v{CONTRACT_VERSION} / schema v{SCHEMA_VERSION}"
