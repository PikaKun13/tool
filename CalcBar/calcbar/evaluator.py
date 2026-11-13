"""Python の文法で書いた式を評価する。

設計方針：
  * 式は 100% Python の書き方：``2**3`` は 8、``10//3`` は 3、``^`` は XOR。
  * math モジュールの関数・定数は ``math.`` なしでそのまま使える：``tanh(2)``、``pi``、``sqrt(2)``。
  * 純粋な計算だけを許す：属性アクセス、import、lambda、添字などは禁止し、任意のコード実行に使われないようにする。
"""

from __future__ import annotations

import ast
import math
import re
import sys
from dataclasses import dataclass, field
from typing import Any

# 大きな整数を文字列にするときの既定の上限は 4300 桁。2**50000 のような結果も表示できるよう少し引き上げる。
try:
    sys.set_int_max_str_digits(200_000)
except AttributeError:  # pragma: no cover - 3.11 より前にはこの関数がない
    pass


class SafetyError(Exception):
    """式に許可されていない構文が含まれている。"""


# --------------------------------------------------------------------------
# 1. 記号の正規化：入力しにくい記号や Python にない記号を Python に翻訳する
# --------------------------------------------------------------------------

# 1 対 1 でそのまま置き換える記号
_CHAR_MAP = {
    "×": "*", "·": "*", "∗": "*", "✕": "*", "✖": "*",
    "÷": "/", "∕": "/", "⁄": "/",
    "−": "-", "–": "-", "—": "-",
    "π": "pi", "𝜋": "pi", "τ": "tau", "∞": "inf",
    "≠": "!=", "≤": "<=", "≥": ">=",
    "，": ",", "（": "(", "）": ")", "　": " ",
}

# 全角文字 -> 半角
_FULLWIDTH = str.maketrans(
    "０１２３４５６７８９＋－＊／．，％＾＝＜＞！（）",
    "0123456789+-*/.,%^=<>!()",
)

# 上付き文字 -> 指数
_SUPERSCRIPT = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁻": "-", "⁺": "+",
}
_SUPERSCRIPT_RE = re.compile("[" + "".join(_SUPERSCRIPT) + "]+")

# 前置の関数記号：√9 -> sqrt(9)
_PREFIX_FUNCS = {"√": "sqrt", "∛": "cbrt"}

_OPERAND_RE = re.compile(r"\d+\.?\d*|\.\d+|[A-Za-z_]\w*")


def _expand_prefix(text: str, ch: str, func: str) -> str:
    """``√9`` / ``√x`` を ``sqrt(9)`` / ``sqrt(x)`` に展開する。``√(..)`` は名前だけ置き換える。"""
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
            i = j                      # 後ろの '(' は次の周回でそのままコピーする
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
    """ユーザーの入力を、正しい Python の式のテキストに翻訳する。"""
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
    """足りない閉じ括弧を補い、入力しながら計算できるようにする。

    ``(補った後の式, 正しいかどうか)`` を返す。閉じ括弧が多すぎれば正しくない。
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
# 2. 名前空間：math のすべて + 一部の組み込み関数
# --------------------------------------------------------------------------

_SAFE_BUILTINS = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "pow": pow, "divmod": divmod, "int": int, "float": float,
    "complex": complex, "bool": bool, "len": len, "bin": bin,
    "hex": hex, "oct": oct, "sorted": sorted, "range": range,
    "all": all, "any": any,
}


def build_namespace() -> dict[str, Any]:
    """math の公開メンバー + 安全な組み込み関数 + いくつかの別名。"""
    ns: dict[str, Any] = {
        name: getattr(math, name) for name in dir(math) if not name.startswith("_")
    }
    ns.update(_SAFE_BUILTINS)      # 組み込みの pow/abs のほうが math.pow/fabs より使いやすいので、後から上書きする
    ns["ln"] = math.log            # 自然対数の慣用的な書き方
    # 虚数単位。Python が認めるのは 4j のように「数字にくっついた」リテラルだけで、j 単体はただの名前になる。
    # パネルの j ボタンが挿入するのは j 単体なので、ここで値を与えておく。4j は従来どおりリテラルとして解析される。
    ns["j"] = 1j
    ns["ans"] = 0
    return ns


# --------------------------------------------------------------------------
# 3. AST のホワイトリスト検査
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
# 画面ではキーを 1 つ打つたびに計算するので、いつまでも終わらない式は止める
_MAX_RESULT_BITS = 5_000_000          # 10 進でおよそ 150 万桁
_HEAVY_FUNCS = {"factorial": 5_000, "comb": 20_000, "perm": 20_000}


def _pow_is_huge(base: float, exponent: float) -> bool:
    """実際に計算する前に、``base ** exponent`` がとんでもなく大きくならないか見積もる。"""
    if exponent <= 0 or abs(base) <= 1:
        return False                  # 負の指数なら小数になり、底が 1 以下なら結果も大きくならない
    try:
        return exponent * math.log2(abs(base)) > _MAX_RESULT_BITS
    except (ValueError, OverflowError):
        return True


def _const_number(node: ast.AST, depth: int = 0) -> float | None:
    """定数だけの部分木の値を求める。求められなければ None を返し、大きくなりすぎるものはその場で SafetyError を投げる。"""
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
            raise SafetyError("結果が大きすぎます")
        try:
            return base ** exponent
        except (OverflowError, ZeroDivisionError, ValueError):
            return None
    return None


def still_typing(tree: ast.AST, namespace: dict[str, Any]) -> bool:
    """構文としては正しいが、明らかに書きかけ——赤字は出さず、``2+`` と同じ扱いにする。

    ひと目でわかる 2 つの場合だけを認め、ほかはふつうにエラーにする（``nosuch(2)`` はやはり知らせる）。
    """
    for node in ast.walk(tree):
        # パネルの sqrt() ボタンを押した直後で、カーソルが括弧の中で引数を待っている
        if isinstance(node, ast.Call) and not node.args and not node.keywords:
            return True
    # 名前を途中まで打ったところ：sqrt と手で打つ途中で s、sq、sqr を経由する
    body = getattr(tree, "body", None)
    return isinstance(body, ast.Name) and body.id not in namespace


def validate(tree: ast.AST) -> None:
    """AST をたどり、許可されていない書き方があればすぐ SafetyError を投げる。"""
    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > _MAX_NODES:
            raise SafetyError("式が長すぎます")
        if not isinstance(node, _ALLOWED_NODES):
            raise SafetyError(f"対応していない書き方: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise SafetyError("アンダースコアで始まる名前は使えません")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise SafetyError("関数は名前で直接呼び出してください")
            if any(kw.arg is None for kw in node.keywords):
                raise SafetyError("** による展開には対応していません")
            limit = _HEAVY_FUNCS.get(node.func.id)
            if limit is not None and node.args:
                arg = _const_number(node.args[0])
                if arg is not None and arg > limit:
                    raise SafetyError(f"{node.func.id} の引数が大きすぎます")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            _const_number(node)        # 定数のべき乗が大きすぎると SafetyError を投げる


# --------------------------------------------------------------------------
# 4. 結果の整形
# --------------------------------------------------------------------------

_MAX_DISPLAY = 220


def format_value(value: Any) -> str:
    """Python の表示の流儀で結果をテキストにする（callable なら空文字列を返し、表示しない）。"""
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
        except ValueError:      # 長すぎる整数
            return "<桁数が多すぎます>"
    return repr(value)


def shorten(text: str, limit: int = _MAX_DISPLAY) -> str:
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    return f"{text[:head]}…{text[-(limit - head - 1):]}"


# --------------------------------------------------------------------------
# 5. 公開インターフェース
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 5.5 複数行のスクリプト：1 行 1 ステップ。どのステップの結果を見せるかは show で決める
# --------------------------------------------------------------------------

MAX_LINES = 40          # キーを打つたびに全体を再計算するので、行数には上限が要る

# スペースと括弧の 2 通りの書き方を受け付ける：`show b` と `show(b)`。
# 後者は show の部分だけを取り除き、括弧は残す——`(b)` を評価すればもともと `b` と同じ。
_SHOW_RE = re.compile(r"^\s*show\b\s*(.+)$", re.S)
# 'show' の直後に演算子が来るなら、被演算子として使われている（show = 5 / show - 1）
_OPERAND_HINT = set("=+-*/%<>!&|^~),].:")


def strip_show(line: str) -> tuple[str, bool]:
    """行頭の ``show`` を取り除き、``(式, 表示するかどうか)`` を返す。

    ``show`` は Python のキーワードではなく、ユーザーが変数名に使うこともありうるので、取り除く前に
    残りが本当に式であることを確かめる。そうでなければ何もしない。
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
    """スクリプトの 1 行。``shown`` が真なら画面に ``result`` を表示する。"""

    index: int              # 元のテキストでの行番号（0 始まり）
    source: str             # show を取り除いた後の式のテキスト
    shown: bool
    result: "EvalResult"


@dataclass
class EvalResult:
    """1 回の評価の結果。``display`` が空なら画面には何も表示しない。"""

    display: str = ""
    value: Any = None
    error: str | None = None
    note: str | None = None
    incomplete: bool = False        # まだ書きかけ（構文が不完全）。エラーを出して驚かせない
    assigned: str | None = None
    source: str = ""                # 正規化 + 括弧を補った後の式

    @property
    def ok(self) -> bool:
        return self.error is None and not self.incomplete


_ERROR_TEXT = {
    ZeroDivisionError: "0 で割ることはできません",
    OverflowError: "結果が大きすぎます",
    RecursionError: "式の入れ子が深すぎます",
    MemoryError: "メモリが足りません",
}


def _describe_error(exc: BaseException) -> str:
    for exc_type, text in _ERROR_TEXT.items():
        if isinstance(exc, exc_type):
            return text
    if isinstance(exc, NameError):
        name = re.search(r"'([^']+)'", str(exc))
        return f"{name.group(1)} という関数や変数はありません" if name else "名前が定義されていません"
    if isinstance(exc, TypeError):
        return f"使い方が正しくありません: {exc}"
    if isinstance(exc, ValueError):
        msg = str(exc)
        if "domain error" in msg:
            return "関数の定義域の外です"
        return msg or "値が正しくありません"
    if isinstance(exc, SafetyError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


class Evaluator:
    """Python の意味どおりに式を計算し、``ans`` とユーザー定義の変数を覚えておく。"""

    def __init__(self) -> None:
        self.namespace = build_namespace()

    def reset(self) -> None:
        self.namespace = build_namespace()

    # -- 内部 -------------------------------------------------------------
    def _parse(self, source: str) -> tuple[ast.AST, str, str | None]:
        """(AST, コンパイルモード, 代入先の変数名) を返す。"""
        try:
            return ast.parse(source, mode="eval"), "eval", None
        except SyntaxError:
            pass
        tree = ast.parse(source, mode="exec")       # SyntaxError を投げることがある。上の層に任せる
        if len(tree.body) != 1:
            raise SyntaxError("一度に書ける式は 1 つだけです")
        stmt = tree.body[0]
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise SyntaxError("代入できるのは変数 1 つだけです")
            return tree, "exec", stmt.targets[0].id
        if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            return tree, "exec", stmt.target.id
        raise SyntaxError("式を入力してください")

    # -- 公開 -------------------------------------------------------------
    def evaluate(self, expr: str) -> EvalResult:
        raw = normalize(expr)
        if not raw:
            return EvalResult()

        source, balanced = balance_parens(raw)
        if not balanced:
            return EvalResult(error="閉じ括弧が多すぎます", source=source)

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
        except Exception as exc:                    # noqa: BLE001 - ユーザーに見せる
            return EvalResult(error=_describe_error(exc), source=source)

        note = None
        if any(isinstance(n, ast.BitXor) for n in ast.walk(tree)):
            note = "^ はビット単位の XOR です。べき乗は ** を使ってください"

        display = format_value(value)
        if assigned and display:
            display = f"{assigned} = {display}"
        return EvalResult(display=display, value=value, note=note,
                          assigned=assigned, source=source)

    def evaluate_script(self, text: str) -> list[LineResult]:
        """複数行モード：1 行ずつ評価し、名前空間は共有する。

        ある行がエラーでも後ろの行は止めない——入力しながら計算しているとき、下の行はまだ形になっていないのがふつうで、
        エラーのたびに全体が止まると、ちらついてひどく見づらい。
        """
        lines = text.split("\n")[:MAX_LINES]
        last = max((i for i, line in enumerate(lines) if line.strip()), default=-1)

        out: list[LineResult] = []
        for i, raw in enumerate(lines):
            if not raw.strip():
                continue
            source, shown = strip_show(raw)
            result = self.evaluate(source)
            # エラーの行は必ず表示する：show がないからといって黙って失敗するのがいちばん困る。
            # 「書きかけ」はエラーではない（error は None）ので、入力中に赤字がちらつくことはない。
            out.append(LineResult(index=i, source=source,
                                  shown=shown or i == last or result.error is not None,
                                  result=result))
        return out

    def commit(self, result: EvalResult) -> None:
        """成功した計算の結果を ``ans`` として記録する。"""
        if result.ok and result.value is not None and not callable(result.value):
            self.namespace["ans"] = result.value
