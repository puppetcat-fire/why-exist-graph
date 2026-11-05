"""静态检查：函数体里引用了、但模块内没有定义的全局名。

这类 bug 不会在 import 时报错，只有跑到那条分支才 `NameError`——`cmd_init` 缺
`db_url`/`re` 的导入、`repo-add` 缺 `_is_integrity_error` 都是这个形态，而且都
只在非 SQLite 后端或 path 冲突时才触发，常规测试与 CI 都碰不到。
`python -m py_compile` 也查不出来（名字查找发生在运行期）。

实现用标准库 `symtable`：它给出每个作用域的解析结果，`is_global()` 就表示
「这个名字在本作用域里按全局解析」。拿它和模块级定义对比，比手写 AST 遍历
（还要处理闭包、嵌套函数、except-as、推导式）可靠得多。

跑法：
    python tools/check_undefined.py            # 检查 scripts/ 下全部 .py
    python tools/check_undefined.py path ...   # 检查指定文件

退出码 0 = 干净；1 = 有未定义名。

已知边界：只判断「模块级有没有这个名字」，不做跨模块解析。所以它可能
**漏报**（从别处 import 进来但用错名字时，那个名字在模块里存在）也可能
**误报**（`globals()` 动态注入的名字），但对「忘了 import」这一类命中很高。
"""

from __future__ import annotations

import builtins
import sys
import symtable
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
DEFAULT_ROOT = SKILL / "scripts"


def check_source(source: str, filename: str) -> list[tuple[int, str]]:
    try:
        top = symtable.symtable(source, filename, "exec")
    except SyntaxError as exc:
        return [(exc.lineno or 0, f"<语法错误：{exc.msg}>")]

    module_names = {symbol.get_name() for symbol in top.get_symbols()}
    module_names |= {"__name__", "__file__", "__doc__", "__package__", "__spec__", "__builtins__"}
    problems: list[tuple[int, str]] = []

    def walk(table: symtable.SymbolTable, prefix: str) -> None:
        if prefix:  # 模块级符号都是定义，不用查
            for symbol in table.get_symbols():
                name = symbol.get_name()
                if not symbol.is_global():
                    continue
                if name in module_names or hasattr(builtins, name):
                    continue
                label = f"{prefix}{name}"
                problems.append((0, label))
        for child in table.get_children():
            walk(child, f"{prefix}{child.get_name()}.")

    walk(top, "")
    return sorted(set(problems))


def check_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [(0, f"<解码失败：{exc}>")]
    return check_source(source, str(path))


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    paths = [Path(item) for item in args] if args else sorted(DEFAULT_ROOT.rglob("*.py"))

    bad = 0
    for path in paths:
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        problems = check_file(path)
        if not problems:
            continue
        bad += 1
        label = path.relative_to(SKILL) if path.is_relative_to(SKILL) else path
        print(f"{label}:")
        for lineno, detail in problems:
            print(f"  {lineno:>5}  {detail}" if lineno else f"       {detail}")

    if bad:
        print(f"\n未定义名：{bad} 个文件有问题")
        return 1
    print(f"未定义名：{len(paths)} 个文件，全部干净")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
