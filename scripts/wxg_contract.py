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

SCHEMA_VERSION = 3
CONTRACT_VERSION = "0.4.0"

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

# 这些条件代表“行为已经跑过”；置真前必须有 exit_code=0 的 evidence 记录。
EVIDENCE_REQUIRED_CONDITIONS = ["BehaviorPassed"]

GATE_RULES = [
    "条件未齐（七项条件与 Ready 任一为假）→ FAIL。",
    "作用域内存在 UNNECESSARY 或 HOLLOW，且没有任何 KEEP 反证 → FAIL；咬合只采信 `bites` 表（含 actor），`attrs.bite` 仅供展示。",
    "gate 只读：不写条件、不写工单、不改节点，重复执行结果不变；PASS 退出码 0、FAIL 退出码 1。",
    "除 Accepted 由 `feature-declare` / `feature-register` 新建时置真外，只有 work-judge(passed) 写条件；judge(failed) 把该条件及其后的条件置假，没有对应条件的工单（scan）不改条件。",
    "`BehaviorPassed` 置真前必须有一条**同 generation**、exit_code=0 且产物有效的 evidence（有产物时校验存在与 hash），gate 执行同样的检查。",
    "`retract` 会级联删除 bite；外部遗留的悬空 bite 不计入门禁（输出 ignored_dangling_bites），由 doctor 清理。",
]

AUDIT_RULES = [
    "`work-claim`、`work-judge`、`bite` 必须带 `--actor`（或 `WXG_ACTOR` 环境变量），记录到 `work_items.claimed_by` / `judged_by` / `bites.actor`。",
    "审计独立性：`work-judge --actor` 不得等于被审工单的 `claimed_by`；旧库迁移写入的 `legacy` 允许，但结果会带 `legacy_claim: true`，doctor 报 `legacy-identity`（不可追溯，不伪造成员）。",
    "`work-judge` 同时写 `judged_at`；一个工单的 `judged_by` 不允许被后续裁决覆盖（仅允许从空到有值）。",
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

# ---------------------------------------------------------------- 角色

ROLES = {
    "scan": ["import-file", "upsert-node", "retract", "get", "find", "slice", "work-finish", "role-prompt"],
    "model-architecture": ["upsert-node", "upsert-edge", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "model-structure": ["upsert-node", "upsert-edge", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "interact": ["upsert-node", "upsert-edge", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "specify-test": ["upsert-node", "upsert-edge", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "implement-test": ["upsert-node", "bind", "get", "find", "slice", "work-finish", "role-prompt"],
    "observe": ["import-file", "upsert-node", "retract", "get", "find", "slice", "work-finish", "role-prompt"],
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
    "sample": C(
        "从仓里均匀随机取一个节点，作为撕咬入口",
        options=[O("--repo", required=True), O("--seed", type=int, default=None)],
    ),
    "feature-declare": C(
        "声明功能：generation+1，重置条件，只派 work-seed",
        options=[
            O("--id", required=True),
            O("--name", required=True),
            O("--statement", required=True),
            O("--acceptance", required=True, help="JSON 数组，或 @文件"),
            O("--constraints", required=True, help="JSON 数组，或 @文件"),
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
    "work-open": C(
        "预开/扩展非 audit 工单的 target_ids（scan 与设计角色扩写入边界都用它）",
        options=[
            O("--feature", required=True),
            O("--kind", required=True, choices=WORK_KINDS),
            O("--target-ids", required=True, help="JSON 数组或 @文件"),
        ],
    ),
    "work-seed": C("按缺的条件各生成一张工单", options=[O("--feature", required=True)]),
    "work-claim": C(
        "按角色领取当前代一张 ready 工单，返回 claim_token 与切片",
        options=[
            O("--role", required=True, choices=sorted(ROLES)),
            O("--actor", default=None, help="领取者 id；也可用 WXG_ACTOR 环境变量"),
        ],
        flags=[F("--allow-product-code", help="implement-test 专用：当轮明确允许改产品代码")],
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
        options=[O("--token", required=True), O("--node-ids", default=None, help="JSON 数组或 @文件"), O("--edge-ids", default=None, help="JSON 数组或 @文件")],
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
    "gate": C("交付门：只读计算 PASS/FAIL；PASS 退出码 0、FAIL 退出码 1", options=[O("--feature", required=True)], flags=[F("--json")]),
    "export": C("按 feature 导出六份只读视图（写入 <root>/export/）", options=[O("--feature", required=True)]),
    "slice": C("取工单或 target_ids 的深度 1 切片（只读；target_ids 支持 `前缀*` 与 @文件）", options=[O("--work", default=None), O("--ids", default=None, help="JSON 数组或 @文件")]),
    "get": C("按 id 读取一个节点", options=[O("--id", required=True)]),
    "find": C("按 kind / 路径前缀 / 入边起点查找节点", options=[O("--kind", default=None, choices=[k["kind"] for k in NODE_KINDS]), O("--path-prefix", default=None), O("--from-id", default=None)]),
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
    "repo-add": "状态库",
    "repo-list": "只读",
    "import-file": "写图需 claim_token；--prepare 免 token",
    "sample": "只读",
    "feature-declare": "状态库",
    "feature-register": "状态库",
    "feature-list": "只读",
    "feature-status": "只读",
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
    "component": {"duty": "str"},
    "port": {"port": "int", "protocol": "str"},
    "classifier": {"duty": "str"},
    "property": {"column": "str"},
    "operation": {"http": "str", "success_code": "str", "async": "bool"},
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
    "04 取用例经 depends/associates/realizes 到达的 component 与 port；05 取用例 contains 的 operation 及其 has_input、"
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
    ("I9 状态可自检", "doctor 检查悬空 bite/边/引用、陈旧 token、条件完整性、审计配对、legacy 身份与证据产物；--fix 只清理悬空引用与陈旧 token，不替人裁决。"),
    ("I10 审计可追溯", "work-claim / work-judge / bite 记录 actor；审计 actor 不得等于被审工单的 claimed_by；judged_by/judged_at 只写一次；gate 采信的咬合以 bites 表为准。"),
    ("I11 证据可追溯", "evidence-record 把命令、退出码、generation、执行者、产物 SHA-256 写入 evidence 表；doctor 校验产物存在/hash/退出码/generation 非空与 legacy 身份；judge/gate 对 BehaviorPassed 强制同代、exit_code=0 且产物有效的 evidence；重跑证据不得改写权威状态。"),
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
    lines.append("| 规则 |")
    lines.append("|------|")
    for rule in GATE_RULES:
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
        "evidence_required_conditions": EVIDENCE_REQUIRED_CONDITIONS,
        "gate_rules": GATE_RULES,
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
