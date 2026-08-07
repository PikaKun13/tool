"""面板里每个公式都真的算对了吗？

这里刻意**不拿 math.xxx 当标准答案**——那等于自己验自己。参照物一律另找：
闭式解、暴力枚举、恒等式、反函数还原、Decimal 高精度、以及跟原生 Python 差分。
"""

import ast
import itertools
import math
import random
import re
import sys
import unittest
from decimal import Decimal, getcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calcbar.evaluator import Evaluator, build_namespace   # noqa: E402
from calcbar.symbols import SECTIONS                       # noqa: E402

getcontext().prec = 40

ALL_ITEMS = [item for section in SECTIONS for item in section.items]


class FormulaCase(unittest.TestCase):
    """带一个求值器，外加「算出来的值」和「约等于」两个小工具。"""

    def setUp(self):
        self.ev = Evaluator()

    def val(self, expr):
        result = self.ev.evaluate(expr)
        self.assertTrue(result.ok, f"{expr} 没算出来：{result.error or '语法不完整'}")
        return result.value

    def near(self, expr, expected, tol=1e-12):
        got = self.val(expr)
        self.assertLessEqual(abs(got - expected), tol * max(1.0, abs(expected)),
                             f"{expr} = {got!r}，参照值 {expected!r}")


# --------------------------------------------------------------------------
# 参照实现：全部用定义式硬算，不碰 math
# --------------------------------------------------------------------------

def ref_factorial(n):
    out = 1
    for i in range(2, n + 1):
        out *= i
    return out


def ref_gcd(a, b):
    return max(d for d in range(1, min(a, b) + 1) if a % d == 0 == b % d)


def ref_lcm(a, b):
    return min(m for m in range(1, a * b + 1) if m % a == 0 and m % b == 0)


def ref_isqrt(n):
    i = 0
    while (i + 1) ** 2 <= n:
        i += 1
    return i


def taylor_sin(x, terms=40):
    x = Decimal(x)
    out, term = Decimal(0), x
    for k in range(terms):
        out += term
        term *= -x * x / ((2 * k + 2) * (2 * k + 3))
    return float(out)


def taylor_cos(x, terms=40):
    x = Decimal(x)
    out, term = Decimal(0), Decimal(1)
    for k in range(terms):
        out += term
        term *= -x * x / ((2 * k + 1) * (2 * k + 2))
    return float(out)


class PanelIsWiredUpTest(FormulaCase):
    """面板上的每个按钮都得指向真实存在的东西。"""

    def test_every_function_button_names_a_real_function(self):
        ns = build_namespace()
        for item in ALL_ITEMS:
            if not item.insert.endswith("()") or item.insert == "()":
                continue
            name = item.insert[:-2]
            with self.subTest(button=item.label):
                self.assertIn(name, ns)
                self.assertTrue(callable(ns[name]), f"{name} 不是函数")

    def test_every_constant_button_evaluates(self):
        for item in ALL_ITEMS:
            if item.insert.endswith("()") or item.insert in ("**", "//", "%", ","):
                continue
            with self.subTest(button=item.label):
                self.assertTrue(self.ev.evaluate(item.insert).ok)

    def test_no_button_makes_the_bar_flash_red_on_its_own(self):
        """点一下按钮就蹦红字是吓人的：刚插进去最多算「还没打完」。"""
        for item in ALL_ITEMS:
            with self.subTest(button=item.label):
                result = self.ev.evaluate(item.insert)
                self.assertIsNone(result.error,
                                  f"插入 {item.insert!r} 报了「{result.error}」")


class ConstantsTest(FormulaCase):
    def test_pi_matches_forty_known_digits(self):
        self.near("pi", float(Decimal(
            "3.14159265358979323846264338327950288419716939937510")), 1e-15)

    def test_e_matches_decimal_exp_of_one(self):
        self.near("e", float(Decimal(1).exp()), 1e-15)

    def test_tau_is_exactly_two_pi(self):
        self.assertEqual(self.val("tau"), self.val("2*pi"))

    def test_inf_is_infinite(self):
        self.assertEqual(self.val("inf"), float("inf"))

    def test_j_is_the_imaginary_unit(self):
        self.assertEqual(self.val("1j*1j"), complex(-1, 0))
        self.assertEqual(self.val("abs(3+4j)"), 5.0)

    def test_ans_starts_at_zero(self):
        self.assertEqual(self.val("ans"), 0)


class RootsAndPowersTest(FormulaCase):
    def test_sqrt_matches_decimal_and_squares_back(self):
        self.near("sqrt(2)", float(Decimal(2).sqrt()), 1e-15)
        for n in range(1, 200):
            self.near(f"sqrt({n})**2", n)

    def test_cbrt_cubes_back(self):
        self.near("cbrt(27)", 3.0, 1e-15)
        for n in range(1, 200):
            self.near(f"cbrt({n})**3", n)

    def test_pow_agrees_with_the_star_star_operator(self):
        for a in range(2, 8):
            for b in range(0, 6):
                self.assertEqual(self.val(f"pow({a},{b})"), self.val(f"{a}**{b}"))


class LogarithmTest(FormulaCase):
    def test_exp_matches_decimal(self):
        self.near("exp(1)", float(Decimal(1).exp()), 1e-15)
        self.assertEqual(self.val("exp(0)"), 1.0)

    def test_ln_is_natural_not_common(self):
        self.near("ln(10)", float(Decimal(10).ln()), 1e-15)
        self.assertEqual(self.val("ln(1)"), 0.0)
        self.assertEqual(self.val("ln(e)"), 1.0)

    def test_ln_undoes_exp(self):
        for n in range(1, 50):
            self.near(f"ln(exp({n}))", n)

    def test_log_defaults_to_natural_and_takes_a_base(self):
        self.assertEqual(self.val("log(e)"), 1.0)
        self.near("log(100, 10)", 2.0, 1e-15)

    def test_log2_and_log10_invert_their_powers(self):
        for k in range(0, 40):
            self.assertEqual(self.val(f"log2(2**{k})"), float(k))
        for k in range(0, 16):
            self.assertEqual(self.val(f"log10(10**{k})"), float(k))


class TrigonometryTest(FormulaCase):
    def test_known_exact_angles(self):
        self.near("sin(pi/6)", 0.5, 1e-15)
        self.near("cos(pi/3)", 0.5, 1e-15)
        self.near("tan(pi/4)", 1.0, 1e-15)

    def test_sin_and_cos_match_a_taylor_series(self):
        self.near("sin(1)", taylor_sin(1), 1e-15)
        self.near("cos(1)", taylor_cos(1), 1e-15)

    def test_pythagorean_identity_holds(self):
        for x in range(-30, 31):
            self.near(f"sin({x / 7})**2+cos({x / 7})**2", 1.0, 1e-14)

    def test_tan_is_sin_over_cos(self):
        for x in range(-10, 11):
            self.near(f"tan({x / 9})", self.val(f"sin({x / 9})/cos({x / 9})"))

    def test_inverse_functions_round_trip(self):
        for x in range(-30, 31):
            self.near(f"asin(sin({x / 20}))", x / 20)
            self.near(f"atan(tan({x / 20}))", x / 20)
        for x in range(0, 61):
            self.near(f"acos(cos({x / 20}))", x / 20)

    def test_atan2_knows_its_quadrant(self):
        self.near("atan2(1, 1)", math.pi / 4, 1e-15)
        self.near("atan2(1, -1)", 3 * math.pi / 4, 1e-15)


class HyperbolicTest(FormulaCase):
    def test_sinh_and_cosh_match_their_definitions(self):
        for x in range(-20, 21):
            self.near(f"sinh({x / 5})", self.val(f"(exp({x / 5})-exp(-{x / 5}))/2"))
            self.near(f"cosh({x / 5})", self.val(f"(exp({x / 5})+exp(-{x / 5}))/2"))

    def test_hyperbolic_identity_holds(self):
        for x in range(-20, 21):
            self.near(f"cosh({x / 5})**2-sinh({x / 5})**2", 1.0, 1e-11)

    def test_tanh_is_sinh_over_cosh(self):
        for x in range(-20, 21):
            self.near(f"tanh({x / 5})", self.val(f"sinh({x / 5})/cosh({x / 5})"))


class AngleConversionTest(FormulaCase):
    def test_half_turn_is_180_degrees(self):
        self.near("degrees(pi)", 180.0, 1e-15)
        self.near("radians(180)", math.pi, 1e-15)

    def test_the_two_are_inverses(self):
        for d in range(0, 361, 7):
            self.near(f"degrees(radians({d}))", d)

    def test_degrees_is_the_textbook_formula(self):
        for x in range(-10, 11):
            self.near(f"degrees({x / 3})", self.val(f"{x / 3}*180/pi"))


class RoundingTest(FormulaCase):
    def test_floor_ceil_and_trunc_differ_where_they_should(self):
        for x in (-3.7, -2.5, -0.2, 0.0, 0.2, 2.5, 3.7):
            whole = int(x)
            with self.subTest(x=x):
                self.assertEqual(self.val(f"floor({x})"),
                                 whole if x >= 0 or x == whole else whole - 1)
                self.assertEqual(self.val(f"ceil({x})"),
                                 whole if x <= 0 or x == whole else whole + 1)
                self.assertEqual(self.val(f"trunc({x})"), whole)

    def test_round_is_banker_s_rounding(self):
        got = [self.val(f"round({x})")
               for x in (0.5, 1.5, 2.5, 3.5, -0.5, -1.5, -2.5)]
        self.assertEqual(got, [0, 2, 2, 4, 0, -2, -2])

    def test_floor_x_plus_half_is_the_old_school_rounding(self):
        got = [self.val(f"floor({x}+0.5)") for x in (0.5, 1.5, 2.5, 3.5)]
        self.assertEqual(got, [1, 2, 3, 4])


class IntegerFunctionTest(FormulaCase):
    def test_isqrt_matches_a_counting_loop(self):
        for n in range(0, 301):
            self.assertEqual(self.val(f"isqrt({n})"), ref_isqrt(n))

    def test_factorial_matches_a_product_loop(self):
        for n in range(0, 61):
            self.assertEqual(self.val(f"factorial({n})"), ref_factorial(n))

    def test_gcd_matches_brute_force_search(self):
        for a in range(1, 41):
            for b in range(1, 41):
                self.assertEqual(self.val(f"gcd({a}, {b})"), ref_gcd(a, b))

    def test_lcm_matches_brute_force_search(self):
        for a in range(1, 26):
            for b in range(1, 26):
                self.assertEqual(self.val(f"lcm({a}, {b})"), ref_lcm(a, b))

    def test_gcd_times_lcm_is_the_product(self):
        for a in range(1, 31):
            for b in range(1, 31):
                self.assertEqual(self.val(f"gcd({a},{b})*lcm({a},{b})"), a * b)

    def test_comb_matches_itertools_counting(self):
        for n in range(0, 11):
            for k in range(0, n + 1):
                self.assertEqual(self.val(f"comb({n}, {k})"),
                                 sum(1 for _ in itertools.combinations(range(n), k)))

    def test_perm_matches_itertools_counting(self):
        for n in range(0, 9):
            for k in range(0, n + 1):
                self.assertEqual(self.val(f"perm({n}, {k})"),
                                 sum(1 for _ in itertools.permutations(range(n), k)))

    def test_comb_times_k_factorial_is_perm(self):
        for n in range(0, 11):
            for k in range(0, n + 1):
                self.assertEqual(self.val(f"comb({n},{k})*factorial({k})"),
                                 self.val(f"perm({n},{k})"))


class StatisticsTest(FormulaCase):
    def test_hypot_is_the_pythagorean_distance(self):
        self.assertEqual(self.val("hypot(3, 4)"), 5.0)
        for a in range(0, 15):
            for b in range(0, 15):
                self.near(f"hypot({a}, {b})", self.val(f"sqrt({a}**2+{b}**2)"))

    def test_min_and_max_agree_with_sorting(self):
        for triple in itertools.product(range(-3, 4), repeat=3):
            a, b, c = triple
            self.assertEqual(self.val(f"min({a},{b},{c})"), sorted(triple)[0])
            self.assertEqual(self.val(f"max({a},{b},{c})"), sorted(triple)[-1])

    def test_sum_of_a_range_matches_the_closed_form(self):
        for n in range(0, 200):
            self.assertEqual(self.val(f"sum(range({n}))"), n * (n - 1) // 2)

    def test_abs_handles_reals_and_complex(self):
        self.assertEqual(self.val("abs(-7)"), 7)
        self.assertEqual(self.val("abs(3+4j)"), 5.0)


class TipsAreHonestTest(FormulaCase):
    """按钮悬停时显示的说明里写了等式，那就得真的等于。"""

    CLAIM = re.compile(r"([A-Za-z0-9_()\[\], .*/%+-]*?[)\d])\s*=\s*([-\d.]+)")

    def test_equations_written_in_the_tips_actually_hold(self):
        checked = 0
        for item in ALL_ITEMS:
            for expr, expected in self.CLAIM.findall(item.tip):
                expr = expr.strip()
                if not expr or expr.replace(".", "").replace("-", "").isdigit():
                    continue
                try:
                    ast.parse(expr, mode="eval")
                except SyntaxError:
                    continue
                checked += 1
                with self.subTest(button=item.label, claim=f"{expr} = {expected}"):
                    self.near(expr, float(expected))
        self.assertGreaterEqual(checked, 5, "tip 里的等式一条都没提取到，正则该修了")

    def test_the_prose_in_the_tips_also_holds(self):
        self.assertTrue(str(self.val("pi")).startswith("3.14159"))    # 「3.14159…」
        self.assertTrue(str(self.val("e")).startswith("2.71828"))     # 「2.71828…」
        self.assertEqual(self.val("tau"), 2 * self.val("pi"))         # 「2π」
        self.assertIsInstance(self.val("3+4j"), complex)              # 「如 3+4j」
        self.assertEqual(self.val("sqrt(81)"), 9.0)                   # 「平方根」
        self.near("cbrt(64)", 4.0, 1e-15)                             # 「立方根」
        self.near("exp(3)", self.val("e**3"))                         # 「e 的多少次方」
        self.assertEqual(self.val("log2(64)"), 6.0)                   # 「以 2 为底」
        self.assertEqual(self.val("log10(100000)"), 5.0)              # 「以 10 为底」
        self.near("sin(pi/2)", 1.0, 1e-15)                            # 「参数是弧度」
        self.near("degrees(pi/2)", 90.0, 1e-13)                       # 「弧度转角度」
        self.near("radians(90)", math.pi / 2, 1e-15)                  # 「角度转弧度」
        self.assertEqual(self.val("gcd(48, 180)"), 12)                # 「最大公约数」
        self.assertEqual(self.val("lcm(4, 6)"), 12)                   # 「最小公倍数」
        self.assertEqual(self.val("comb(10, 3)"), 120)                # 「组合数」
        self.assertEqual(self.val("perm(10, 3)"), 720)                # 「排列数」
        self.assertEqual(self.val("sum(range(101))"), 5050)           # 「sum(range(101))」

    def test_the_parenthesis_button_puts_the_caret_inside(self):
        button = next(i for i in ALL_ITEMS if i.label == "( )")
        self.assertEqual(button.caret_back, 1)


class NormalizationKeepsMeaningTest(FormulaCase):
    """好看的符号翻译成 Python 之后，算出来必须一模一样。"""

    PAIRS = [
        ("2×3", "2*3"), ("2·3", "2*3"), ("6÷3", "6/3"), ("5−2", "5-2"),
        ("5–2", "5-2"), ("5—2", "5-2"), ("π", "pi"), ("τ", "tau"), ("∞", "inf"),
        ("1≠2", "1!=2"), ("1≤2", "1<=2"), ("1≥2", "1>=2"),
        ("（１＋２）＊３", "(1+2)*3"), ("max（1，2）", "max(1,2)"),
        ("√9", "sqrt(9)"), ("√(3+6)", "sqrt(3+6)"), ("∛27", "cbrt(27)"),
        ("2²", "2**2"), ("2³", "2**3"), ("10⁻³", "10**-3"), ("2⁻¹⁰", "2**-10"),
        ("3²+4²", "3**2+4**2"), ("√16+∛8", "sqrt(16)+cbrt(8)"),
    ]

    def test_each_pair_evaluates_identically(self):
        for fancy, plain in self.PAIRS:
            with self.subTest(fancy=fancy):
                self.assertEqual(self.val(fancy), self.val(plain))

    def test_fullwidth_digits_are_ordinary_digits(self):
        for i, ch in enumerate("０１２３４５６７８９"):
            self.assertEqual(self.val(ch + "+0"), i)


class DifferentialAgainstPythonTest(FormulaCase):
    """随机造算式，跟原生 Python 逐条比。这是最能兜住意外的一层。"""

    ATOMS = ["1", "2", "3", "7", "0.5", "2.25", "pi", "e", "10", "1_000"]
    UNARY = ["sqrt", "exp", "sin", "cos", "atan", "tanh", "abs", "log10"]
    BINOP = ["+", "-", "*", "/", "//", "%", "**"]

    def build(self, rng, depth=0):
        roll = rng.random()
        if depth > 2 or roll < 0.35:
            return rng.choice(self.ATOMS)
        if roll < 0.55:
            return f"{rng.choice(self.UNARY)}({self.build(rng, depth + 1)})"
        op = rng.choice(self.BINOP)
        right = rng.choice(["2", "3", "0.5"]) if op == "**" else self.build(rng, depth + 1)
        return f"({self.build(rng, depth + 1)}{op}{right})"

    def test_random_expressions_agree_with_native_python(self):
        rng = random.Random(20260807)
        reference = {n: getattr(math, n) for n in dir(math) if not n.startswith("_")}
        reference.update(abs=abs, round=round, min=min, max=max, pow=pow,
                         ln=math.log)

        compared = 0
        for _ in range(3000):
            expr = self.build(rng)
            try:
                expected = eval(expr, {"__builtins__": {}}, dict(reference))
            except Exception:
                continue                       # Python 自己都算不了，不算数
            got = self.ev.evaluate(expr)
            if not got.ok and got.error in ("结果太大了", "算式太长了"):
                continue                       # 界面为了不卡死主动拦掉的
            compared += 1
            with self.subTest(expr=expr):
                self.assertTrue(got.ok, f"Python 算得出 {expected!r}，CalcBar 却说 {got.error}")
                if isinstance(expected, float) and math.isnan(expected):
                    self.assertTrue(math.isnan(got.value))
                else:
                    self.assertEqual(got.value, expected)
        self.assertGreater(compared, 2000, "样本太少，随机生成器可能坏了")


class ReadmeClaimTest(FormulaCase):
    """README 里贴出来的每个结果都得对得上。"""

    ROWS = [
        ("27*27", 729), ("2**3", 8), ("2*3", 6), ("10//3", 3), ("10%3", 1),
        ("4/2", 2.0), ("0.1+0.2", 0.30000000000000004), ("2>1", True),
        ("2^3", 1), ("(1+2)*(3+4)", 21), ("sqrt(2)/2", 0.7071067811865476),
        ("tanh(2)", 0.9640275800758169), ("sqrt(16)", 4.0), ("log(100, 10)", 2.0),
        ("factorial(10)", 3628800), ("degrees(pi)", 180.0), ("hypot(3, 4)", 5.0),
        ("gcd(12, 18)", 6), ("round(0.5)", 0), ("round(1.5)", 2),
        ("round(2.5)", 2), ("round(3.5)", 4), ("round(2.675, 2)", 2.67),
        ("2**100", 1267650600228229401496703205376),
    ]

    def test_every_printed_result_matches(self):
        for expr, expected in self.ROWS:
            with self.subTest(expr=expr):
                got = self.val(expr)
                self.assertEqual(got, expected)
                self.assertIs(type(got), type(expected))

    def test_the_symbol_translation_table_matches(self):
        self.assertEqual(self.val("√9"), self.val("sqrt(9)"))
        self.assertEqual(self.val("3²"), self.val("3**(2)"))
        self.assertEqual(self.val("10⁻³"), self.val("10**(-3)"))

    def test_unclosed_parenthesis_still_calculates(self):
        self.assertEqual(self.ev.evaluate("sqrt(16").value, 4.0)
        self.assertEqual(self.ev.evaluate("1+2)").error, "右括号多了")

    def test_variables_and_ans_behave_as_documented(self):
        self.ev.evaluate("x = 5")
        self.assertEqual(self.val("x**2"), 25)
        self.ev.commit(self.ev.evaluate("25"))
        self.assertEqual(self.val("ans+1"), 26)

    def test_everything_the_readme_promises_to_reject_is_rejected(self):
        for bad in ('__import__("os")', "().__class__", "pi.real", 'open("x")',
                    "(lambda: 1)()", "9**9**9", "factorial(10**9)"):
            with self.subTest(expr=bad):
                self.assertIsNotNone(self.ev.evaluate(bad).error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
