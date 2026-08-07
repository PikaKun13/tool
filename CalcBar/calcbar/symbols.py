"""符号 / 函数选择面板的内容。

每一项 ``Item``：``label`` 是按钮上显示的字，``insert`` 是真正插进输入框的
Python 文本，``caret_back`` 是插入后光标要往回移几格（``sqrt()`` 移 1 格，
光标正好落在括号里）。
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
    Section("运算符 / 常量", (
        Item.token("**", tip="乘方，2**3 = 8"),
        Item.token("//", tip="整除，10//3 = 3"),
        Item.token("%", tip="取余，10%3 = 1"),
        Item("( )", "()", 1, "括号"),
        Item.token(",", tip="分隔多个参数"),
        Item.token("π", "pi", tip="3.14159…"),
        Item.token("e", tip="2.71828…"),
        Item.token("τ", "tau", tip="2π"),
        Item.token("∞", "inf", tip="无穷大"),
        Item.token("ans", tip="上一次的结果"),
        Item.token("j", tip="虚数单位，3+4j；单写 j 就是 1j"),
    )),
    Section("常用函数", (
        Item.func("sqrt", "平方根"),
        Item.func("cbrt", "立方根"),
        Item.func("exp", "e 的多少次方"),
        Item.func("ln", "自然对数"),
        Item.func("log", "log(x) 自然对数 / log(x, 底)"),
        Item.func("log2", "以 2 为底"),
        Item.func("log10", "以 10 为底"),
        Item.func("abs", "绝对值"),
        Item.func("round", "round(x, 位数)；正好 .5 时取偶数，round(2.5)=2"),
        Item.func("pow", "pow(x, y) = x**y"),
    )),
    Section("三角 / 双曲", (
        Item.func("sin", "正弦，参数是弧度"),
        Item.func("cos", "余弦，参数是弧度"),
        Item.func("tan", "正切，参数是弧度"),
        Item.func("asin", "反正弦"),
        Item.func("acos", "反余弦"),
        Item.func("atan", "反正切"),
        Item.func("atan2", "atan2(y, x)"),
        Item.func("sinh", "双曲正弦"),
        Item.func("cosh", "双曲余弦"),
        Item.func("tanh", "双曲正切"),
        Item.func("degrees", "弧度转角度"),
        Item.func("radians", "角度转弧度"),
    )),
    Section("整数 / 统计", (
        Item.func("floor", "向下取整"),
        Item.func("ceil", "向上取整"),
        Item.func("trunc", "去掉小数部分"),
        Item.func("isqrt", "整数平方根"),
        Item.func("factorial", "阶乘"),
        Item.func("gcd", "最大公约数"),
        Item.func("lcm", "最小公倍数"),
        Item.func("comb", "组合数 C(n, k)"),
        Item.func("perm", "排列数 A(n, k)"),
        Item.func("hypot", "hypot(3, 4) = 5"),
        Item.func("min", "最小值"),
        Item.func("max", "最大值"),
        Item.func("sum", "求和，sum(range(101))"),
    )),
)

HINT = ("Enter 复制结果　↑↓ 翻历史　Esc 清空/关闭　Ctrl+K 收起面板　Ctrl+M 多行　"
        "拖左右边缘改宽度　Ctrl+滚轮缩放")

HINT_MULTI = ("Enter 换行　Ctrl+Enter 复制结果　Ctrl+↑↓ 翻历史　"
              "行首 show x 或 show(x) 显示这一步　Ctrl+M 回单行")
