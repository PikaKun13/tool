"""記号 / 関数を選ぶパネルの中身。

各 ``Item``：``label`` はボタンに表示する文字、``insert`` は実際に入力欄に挿入する
Python のテキスト、``caret_back`` は挿入後にカーソルを何文字戻すか（``sqrt()`` なら 1 文字戻して、
カーソルがちょうど括弧の中に来る）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    label: str
    insert: str
    caret_back: int = 0
    tip: str = ""

    @classmethod
    def func(cls, name: str, tip: str = "") -> "Item":
        return cls(f"{name}()", f"{name}()", 1, tip)

    @classmethod
    def token(cls, label: str, insert: str | None = None, tip: str = "") -> "Item":
        return cls(label, insert if insert is not None else label, 0, tip)


@dataclass(frozen=True)
class Section:
    title: str
    items: tuple[Item, ...]


SECTIONS: tuple[Section, ...] = (
    Section("演算子 / 定数", (
        Item.token("**", tip="べき乗、2**3 = 8"),
        Item.token("//", tip="切り捨て除算、10//3 = 3"),
        Item.token("%", tip="剰余、10%3 = 1"),
        Item("( )", "()", 1, "括弧"),
        Item.token(",", tip="複数の引数を区切る"),
        Item.token("π", "pi", tip="3.14159…"),
        Item.token("e", tip="2.71828…"),
        Item.token("τ", "tau", tip="2π"),
        Item.token("∞", "inf", tip="無限大"),
        Item.token("ans", tip="前回の結果"),
        Item.token("j", tip="虚数単位、3+4j。j だけなら 1j"),
    )),
    Section("よく使う関数", (
        Item.func("sqrt", "平方根"),
        Item.func("cbrt", "立方根"),
        Item.func("exp", "e の x 乗"),
        Item.func("ln", "自然対数"),
        Item.func("log", "log(x) 自然対数 / log(x, 底)"),
        Item.func("log2", "底が 2 の対数"),
        Item.func("log10", "底が 10 の対数（常用対数）"),
        Item.func("abs", "絶対値"),
        Item.func("round", "round(x, 桁数)。ちょうど .5 なら偶数へ丸める：round(2.5)=2"),
        Item.func("pow", "pow(x, y) = x**y"),
    )),
    Section("三角 / 双曲線", (
        Item.func("sin", "正弦（引数はラジアン）"),
        Item.func("cos", "余弦（引数はラジアン）"),
        Item.func("tan", "正接（引数はラジアン）"),
        Item.func("asin", "逆正弦"),
        Item.func("acos", "逆余弦"),
        Item.func("atan", "逆正接"),
        Item.func("atan2", "atan2(y, x)"),
        Item.func("sinh", "双曲線正弦"),
        Item.func("cosh", "双曲線余弦"),
        Item.func("tanh", "双曲線正接"),
        Item.func("degrees", "ラジアン → 度"),
        Item.func("radians", "度 → ラジアン"),
    )),
    Section("整数 / 統計", (
        Item.func("floor", "切り捨て（床関数）"),
        Item.func("ceil", "切り上げ（天井関数）"),
        Item.func("trunc", "小数部分を取り除く"),
        Item.func("isqrt", "整数の平方根"),
        Item.func("factorial", "階乗"),
        Item.func("gcd", "最大公約数"),
        Item.func("lcm", "最小公倍数"),
        Item.func("comb", "組み合わせ C(n, k)"),
        Item.func("perm", "順列 P(n, k)"),
        Item.func("hypot", "hypot(3, 4) = 5"),
        Item.func("min", "最小値"),
        Item.func("max", "最大値"),
        Item.func("sum", "合計、sum(range(101))"),
    )),
)

HINT = ("Enter 結果をコピー　↑↓ 履歴　Esc クリア/閉じる　Ctrl+K パネルを閉じる　Ctrl+M 複数行　"
        "左右の端をドラッグで幅を変更　Ctrl+ホイールで拡大縮小")

HINT_MULTI = ("Enter 改行　Ctrl+Enter 結果をコピー　Ctrl+↑↓ 履歴　"
              "行頭に show x か show(x) でその行を表示　Ctrl+M 1 行に戻る")
