"""Python 语法的算式求值器。

设计目标：
  * 算式 100% 按 Python 写：``2**3`` 是 8、``10//3`` 是 3、``^`` 是异或。
  * math 模块的函数/常量直接用，不用写 ``math.``：``tanh(2)``、``pi``、``sqrt(2)``。
  * 只允许纯计算：禁止属性访问、import、lambda、下标等，避免被当成任意代码执行。
"""

from __future__ import annotations

import ast
import math
import re
import sys
from dataclasses import dataclass, field
from typing import Any

# 大整数转字符串默认上限是 4300 位，抬高一点，方便 2**50000 这类结果显示。
try:
    sys.set_int_max_str_digits(200_000)
except AttributeError:  # pragma: no cover - 3.11 以前没有这个函数
    pass


class SafetyError(Exception):
    """算式里出现了不允许的语法。"""


# --------------------------------------------------------------------------
# 1. 符号归一化：把不好输入 / 非 Python 的符号翻译成 Python
# --------------------------------------------------------------------------

# 直接一对一替换的符号
_CHAR_MAP = {
    "×": "*", "·": "*", "∗": "*", "✕": "*", "✖": "*",
    "÷": "/", "∕": "/", "⁄": "/",
    "−": "-", "–": "-", "—": "-",
    "π": "pi", "𝜋": "pi", "τ": "tau", "∞": "inf",
    "≠": "!=", "≤": "<=", "≥": ">=",
    "，": ",", "（": "(", "）": ")", "　": " ",
}

# 全角字符 -> 半角
_FULLWIDTH = str.maketrans(
    "０１２３４５６７８９＋－＊／．，％＾＝＜＞！（）",
    "0123456789+-*/.,%^=<>!()",
)

# 上标 -> 指数
_SUPERSCRIPT = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁻": "-", "⁺": "+",
}
_SUPERSCRIPT_RE = re.compile("[" + "".join(_SUPERSCRIPT) + "]+")

# 前缀函数符号：√9 -> sqrt(9)
_PREFIX_FUNCS = {"√": "sqrt", "∛": "cbrt"}

_OPERAND_RE = re.compile(r"\d+\.?\d*|\.\d+|[A-Za-z_]\w*")


def _expand_prefix(text: str, ch: str, func: str) -> str:
    """把 ``√9`` / ``√x`` 展开成 ``sqrt(9)`` / ``sqrt(x)``；``√(..)`` 只换名字。"""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != ch:
            out.append(text[i])
            i += 1
            continue
        j = i + 1
        while j < n and text[j] == " ":
            j += 1
        if j < n and text[j] == "(":
            out.append(func)
            i = j                      # 后面的 '(' 交给下一轮原样拷贝
            continue
        m = _OPERAND_RE.match(text, j)
        if m:
            out.append(f"{func}({m.group(0)})")
            i = m.end()
            continue
        out.append(func)
        i = j
    return "".join(out)


def normalize(expr: str) -> str:
    """把用户输入翻译成合法的 Python 算式文本。"""
    text = expr.translate(_FULLWIDTH)
    for src, dst in _CHAR_MAP.items():
        if src in text:
            text = text.replace(src, dst)
    for ch, func in _PREFIX_FUNCS.items():
        if ch in text:
            text = _expand_prefix(text, ch, func)
    if _SUPERSCRIPT_RE.search(text):
        text = _SUPERSCRIPT_RE.sub(
            lambda m: "**(" + "".join(_SUPERSCRIPT[c] for c in m.group(0)) + ")",
            text,
        )
    return text.strip()


def balance_parens(expr: str) -> tuple[str, bool]:
    """补上缺失的右括号，方便边打边算。

    返回 ``(补全后的算式, 是否合法)``；右括号多了就是不合法。
    """
    depth = 0
    quote: str | None = None
    for i, ch in enumerate(expr):
        if quote:
            if ch == quote and (i == 0 or expr[i - 1] != "\\"):
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return expr, False
    return expr + ")" * depth, True


# --------------------------------------------------------------------------
# 2. 命名空间：math 的一切 + 少量内置函数
# --------------------------------------------------------------------------

_SAFE_BUILTINS = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "pow": pow, "divmod": divmod, "int": int, "float": float,
    "complex": complex, "bool": bool, "len": len, "bin": bin,
    "hex": hex, "oct": oct, "sorted": sorted, "range": range,
    "all": all, "any": any,
}


def build_namespace() -> dict[str, Any]:
    """math 的公开成员 + 安全内置函数 + 少量别名。"""
    ns: dict[str, Any] = {
        name: getattr(math, name) for name in dir(math) if not name.startswith("_")
    }
    ns.update(_SAFE_BUILTINS)      # 内置 pow/abs 比 math.pow/fabs 好用，故后覆盖
    ns["ln"] = math.log            # 自然对数的习惯写法
    # 虚数单位。Python 只认 4j 这种「贴着数字」的字面量，单写一个 j 是个名字；
    # 面板上的 j 按钮插进来的就是单个 j，所以这里给它一个值。4j 仍按字面量解析。
    ns["j"] = 1j
    ns["ans"] = 0
    return ns


# --------------------------------------------------------------------------
# 3. AST 白名单校验
# --------------------------------------------------------------------------

_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression, ast.Module, ast.Expr, ast.Assign, ast.AugAssign,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.keyword, ast.Name, ast.Constant, ast.Tuple, ast.List,
    ast.Load, ast.Store,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd,
    ast.UAdd, ast.USub, ast.Invert, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)

_MAX_NODES = 400
# 界面每敲一个键就要算一次，所以要挡住会算到天荒地老的算式
_MAX_RESULT_BITS = 5_000_000          # 约 150 万位十进制
_HEAVY_FUNCS = {"factorial": 5_000, "comb": 20_000, "perm": 20_000}


def _pow_is_huge(base: float, exponent: float) -> bool:
    """在真的去算之前，估一下 ``base ** exponent`` 会不会大到爆炸。"""
    if exponent <= 0 or abs(base) <= 1:
        return False                  # 负指数得到小数，底数 ≤1 结果也不会变大
    try:
        return exponent * math.log2(abs(base)) > _MAX_RESULT_BITS
    except (ValueError, OverflowError):
        return True


def _const_number(node: ast.AST, depth: int = 0) -> float | None:
    """算出纯常量子树的值；算不出来返回 None，会爆炸的直接抛 SafetyError。"""
    if depth > 8:
        return None
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _const_number(node.operand, depth + 1)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        base = _const_number(node.left, depth + 1)
        exponent = _const_number(node.right, depth + 1)
        if base is None or exponent is None:
            return None
        if _pow_is_huge(base, exponent):
            raise SafetyError("结果太大了")
        try:
            return base ** exponent
        except (OverflowError, ZeroDivisionError, ValueError):
            return None
    return None


def still_typing(tree: ast.AST, namespace: dict[str, Any]) -> bool:
    """语法上合法，但明显还没写完——这种不该弹红字，跟 ``2+`` 一个待遇。

    只认两种一眼就能看出来的情况，别的照常报错（``nosuch(2)`` 仍要提示）。
    """
    for node in ast.walk(tree):
        # 刚点了面板上的 sqrt() 按钮，光标正停在括号里等着输参数
        if isinstance(node, ast.Call) and not node.args and not node.keywords:
            return True
    # 名字才打了一半：手打 sqrt 的路上会经过 s、sq、sqr
    body = getattr(tree, "body", None)
    return isinstance(body, ast.Name) and body.id not in namespace


def validate(tree: ast.AST) -> None:
    """遍历 AST，遇到不允许的写法直接抛 SafetyError。"""
    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > _MAX_NODES:
            raise SafetyError("算式太长了")
        if not isinstance(node, _ALLOWED_NODES):
            raise SafetyError(f"不支持的写法: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise SafetyError("不能使用下划线开头的名字")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise SafetyError("只能直接调用函数")
            if any(kw.arg is None for kw in node.keywords):
                raise SafetyError("不支持 ** 解包")
            limit = _HEAVY_FUNCS.get(node.func.id)
            if limit is not None and node.args:
                arg = _const_number(node.args[0])
                if arg is not None and arg > limit:
                    raise SafetyError(f"{node.func.id} 的参数太大了")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            _const_number(node)        # 常量幂过大时会抛 SafetyError


# --------------------------------------------------------------------------
# 4. 结果格式化
# --------------------------------------------------------------------------

_MAX_DISPLAY = 220


def format_value(value: Any) -> str:
    """按 Python 的显示习惯把结果转成文本（callable 返回空串，表示不显示）。"""
    if value is None or callable(value):
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        if value != value:
            return "nan"
        if value == math.inf:
            return "inf"
        if value == -math.inf:
            return "-inf"
        return repr(value)
    if isinstance(value, (int, complex, str, tuple, list, range)):
        try:
            return repr(value)
        except ValueError:      # 超长整数
            return "<数字位数过多>"
    return repr(value)


def shorten(text: str, limit: int = _MAX_DISPLAY) -> str:
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    return f"{text[:head]}…{text[-(limit - head - 1):]}"


# --------------------------------------------------------------------------
# 5. 对外接口
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 5.5 多行脚本：一行一步，show 决定哪几步把结果亮出来
# --------------------------------------------------------------------------

MAX_LINES = 40          # 每敲一个键要重算整份，行数得有个头

# 空格和括号两种写法都收：`show b` 和 `show(b)`。
# 后者只把 show 三个字母拿掉，括号留着——`(b)` 求值本来就等于 `b`。
_SHOW_RE = re.compile(r"^\s*show\b\s*(.+)$", re.S)
# 'show' 后面紧跟运算符，说明它是被当成操作数用的（show = 5 / show - 1）
_OPERAND_HINT = set("=+-*/%<>!&|^~),].:")


def strip_show(line: str) -> tuple[str, bool]:
    """剥掉行首的 ``show``，返回 ``(算式, 要不要显示)``。

    ``show`` 不是 Python 关键字，用户完全可以拿它当变量名，所以剥之前先确认
    剩下的部分真是个算式；不是就当没看见。
    """
    match = _SHOW_RE.match(line)
    if not match:
        return line, False
    rest = match.group(1)
    if rest[0] in _OPERAND_HINT:
        return line, False
    probe = normalize(rest)
    for mode in ("eval", "exec"):
        try:
            ast.parse(probe, mode=mode)
            return rest, True
        except SyntaxError:
            continue
    return line, False


@dataclass
class LineResult:
    """脚本里的一行。``shown`` 为真时界面要把 ``result`` 显示出来。"""

    index: int              # 在原文里的行号，0 起
    source: str             # 去掉 show 之后的算式原文
    shown: bool
    result: "EvalResult"


@dataclass
class EvalResult:
    """一次求值的结果。``display`` 为空表示界面上什么都不显示。"""

    display: str = ""
    value: Any = None
    error: str | None = None
    note: str | None = None
    incomplete: bool = False        # 还没打完（语法不完整），不该报错吓人
    assigned: str | None = None
    source: str = ""                # 归一化 + 补全括号之后的算式

    @property
    def ok(self) -> bool:
        return self.error is None and not self.incomplete


_ERROR_TEXT = {
    ZeroDivisionError: "除数不能为 0",
    OverflowError: "结果太大了",
    RecursionError: "算式套得太深",
    MemoryError: "内存不够",
}


def _describe_error(exc: BaseException) -> str:
    for exc_type, text in _ERROR_TEXT.items():
        if isinstance(exc, exc_type):
            return text
    if isinstance(exc, NameError):
        name = re.search(r"'([^']+)'", str(exc))
        return f"没有叫 {name.group(1)} 的函数或变量" if name else "名字未定义"
    if isinstance(exc, TypeError):
        return f"用法不对: {exc}"
    if isinstance(exc, ValueError):
        msg = str(exc)
        if "domain error" in msg:
            return "超出函数定义域"
        return msg or "取值不合法"
    if isinstance(exc, SafetyError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


class Evaluator:
    """按 Python 语义算式子，并记住 ``ans`` 和用户自定义变量。"""

    def __init__(self) -> None:
        self.namespace = build_namespace()

    def reset(self) -> None:
        self.namespace = build_namespace()

    # -- 内部 -------------------------------------------------------------
    def _parse(self, source: str) -> tuple[ast.AST, str, str | None]:
        """返回 (AST, 编译模式, 赋值的变量名)。"""
        try:
            return ast.parse(source, mode="eval"), "eval", None
        except SyntaxError:
            pass
        tree = ast.parse(source, mode="exec")       # 可能抛 SyntaxError，交给上层
        if len(tree.body) != 1:
            raise SyntaxError("一次只能写一条算式")
        stmt = tree.body[0]
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise SyntaxError("只能赋值给一个变量")
            return tree, "exec", stmt.targets[0].id
        if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            return tree, "exec", stmt.target.id
        raise SyntaxError("请输入一个算式")

    # -- 对外 -------------------------------------------------------------
    def evaluate(self, expr: str) -> EvalResult:
        raw = normalize(expr)
        if not raw:
            return EvalResult()

        source, balanced = balance_parens(raw)
        if not balanced:
            return EvalResult(error="右括号多了", source=source)

        try:
            tree, mode, assigned = self._parse(source)
        except SyntaxError:
            return EvalResult(incomplete=True, source=source)

        try:
            validate(tree)
            if still_typing(tree, self.namespace):
                return EvalResult(incomplete=True, source=source)
            code = compile(tree, "<calcbar>", mode)
            if mode == "eval":
                value = eval(code, {"__builtins__": {}}, self.namespace)  # noqa: S307
            else:
                exec(code, {"__builtins__": {}}, self.namespace)  # noqa: S102
                value = self.namespace.get(assigned)
        except SafetyError as exc:
            return EvalResult(error=str(exc), source=source)
        except Exception as exc:                    # noqa: BLE001 - 展示给用户
            return EvalResult(error=_describe_error(exc), source=source)

        note = None
        if any(isinstance(n, ast.BitXor) for n in ast.walk(tree)):
            note = "^ 是按位异或，乘方请用 **"

        display = format_value(value)
        if assigned and display:
            display = f"{assigned} = {display}"
        return EvalResult(display=display, value=value, note=note,
                          assigned=assigned, source=source)

    def evaluate_script(self, text: str) -> list[LineResult]:
        """多行模式：逐行求值，共用一个命名空间。

        某一行算错不打断后面的行——边打边算时下面几行本来就还没成型，
        一出错就整块停摆会闪得很难受。
        """
        lines = text.split("\n")[:MAX_LINES]
        last = max((i for i, line in enumerate(lines) if line.strip()), default=-1)

        out: list[LineResult] = []
        for i, raw in enumerate(lines):
            if not raw.strip():
                continue
            source, shown = strip_show(raw)
            result = self.evaluate(source)
            # 出错的行一律亮出来：没写 show 就闷声失败是最坑人的。
            # 「还没打完」不算错（error 是 None），所以边打边算不会一路飘红。
            out.append(LineResult(index=i, source=source,
                                  shown=shown or i == last or result.error is not None,
                                  result=result))
        return out

    def commit(self, result: EvalResult) -> None:
        """把一次成功的计算记为 ``ans``。"""
        if result.ok and result.value is not None and not callable(result.value):
            self.namespace["ans"] = result.value
