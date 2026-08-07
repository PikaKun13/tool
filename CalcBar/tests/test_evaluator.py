"""求值器的行为约定。用 unittest，跑起来不需要装任何东西。"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calcbar.evaluator import (  # noqa: E402
    Evaluator, balance_parens, format_value, normalize, shorten, strip_show,
)


class PythonSemanticsTest(unittest.TestCase):
    """算式按 Python 写。"""

    def setUp(self):
        self.ev = Evaluator()

    def calc(self, expr):
        return self.ev.evaluate(expr)

    def test_power_uses_double_star(self):
        self.assertEqual(self.calc("2**3").display, "8")

    def test_multiplication(self):
        self.assertEqual(self.calc("2*3").display, "6")

    def test_math_functions_need_no_prefix(self):
        self.assertEqual(self.calc("tanh(2)").display, repr(math.tanh(2)))
        self.assertEqual(self.calc("sqrt(16)").display, "4.0")
        self.assertEqual(self.calc("log10(1000)").display, "3.0")
        self.assertEqual(self.calc("hypot(3, 4)").display, "5.0")

    def test_math_constants(self):
        self.assertEqual(self.calc("pi").display, repr(math.pi))
        self.assertEqual(self.calc("e").display, repr(math.e))
        self.assertEqual(self.calc("tau").display, repr(math.tau))

    def test_ln_alias(self):
        self.assertEqual(self.calc("ln(e)").display, "1.0")

    def test_parentheses_change_precedence(self):
        self.assertEqual(self.calc("(2+3)*4").display, "20")
        self.assertEqual(self.calc("2+3*4").display, "14")
        self.assertEqual(self.calc("((1+2)*(3+4))").display, "21")

    def test_nested_function_calls(self):
        self.assertEqual(self.calc("sqrt(sin(pi/2)+3)").display, "2.0")

    def test_integer_division_and_modulo(self):
        self.assertEqual(self.calc("10//3").display, "3")
        self.assertEqual(self.calc("10%3").display, "1")

    def test_true_division_returns_float_like_python(self):
        self.assertEqual(self.calc("4/2").display, "2.0")

    def test_float_repr_is_pythons(self):
        self.assertEqual(self.calc("0.1+0.2").display, "0.30000000000000004")

    def test_big_integers_are_exact(self):
        self.assertEqual(self.calc("2**100").display, str(2 ** 100))

    def test_comparison_yields_bool(self):
        self.assertEqual(self.calc("2>1").display, "True")
        self.assertEqual(self.calc("1==2").display, "False")

    def test_caret_is_xor_and_is_flagged(self):
        result = self.calc("2^3")
        self.assertEqual(result.display, "1")
        self.assertIn("**", result.note or "")

    def test_builtin_helpers(self):
        self.assertEqual(self.calc("round(2.567, 2)").display, "2.57")
        self.assertEqual(self.calc("max(3, 9, 4)").display, "9")
        self.assertEqual(self.calc("abs(-7)").display, "7")

    def test_underscore_digit_separator(self):
        self.assertEqual(self.calc("1_000*2").display, "2000")

    def test_j_is_the_imaginary_unit_in_any_position(self):
        self.assertEqual(self.calc("3+4j").display, "(3+4j)")   # Python 的字面量
        self.assertEqual(self.calc("j").display, "1j")          # 面板按钮单独插进来
        self.assertEqual(self.calc("j*j").display, "(-1+0j)")
        self.assertEqual(self.calc("2+j").display, "(2+1j)")
        self.assertEqual(self.calc("abs(3+4j)").display, "5.0")


class SymbolInputTest(unittest.TestCase):
    """不好输入的符号可以直接打进去。"""

    def setUp(self):
        self.ev = Evaluator()

    def test_normalize_operators(self):
        self.assertEqual(normalize("2×3"), "2*3")
        self.assertEqual(normalize("6÷3"), "6/3")
        self.assertEqual(normalize("5−2"), "5-2")

    def test_normalize_constants(self):
        self.assertEqual(normalize("π"), "pi")
        self.assertEqual(normalize("2π"), "2pi")   # 语法仍按 Python，需自己写 *

    def test_normalize_roots(self):
        self.assertEqual(normalize("√9"), "sqrt(9)")
        self.assertEqual(normalize("√(3+6)"), "sqrt(3+6)")
        self.assertEqual(normalize("√x"), "sqrt(x)")
        self.assertEqual(normalize("∛27"), "cbrt(27)")

    def test_normalize_superscripts(self):
        self.assertEqual(normalize("2²"), "2**(2)")
        self.assertEqual(normalize("2³"), "2**(3)")
        self.assertEqual(normalize("10⁻³"), "10**(-3)")

    def test_normalize_fullwidth(self):
        self.assertEqual(normalize("（１＋２）＊３"), "(1+2)*3")

    def test_normalize_comparisons(self):
        self.assertEqual(normalize("1≠2"), "1!=2")
        self.assertEqual(normalize("1≤2"), "1<=2")

    def test_symbols_evaluate(self):
        self.assertEqual(self.ev.evaluate("2×3").display, "6")
        self.assertEqual(self.ev.evaluate("√16").display, "4.0")
        self.assertEqual(self.ev.evaluate("3²+4²").display, "25")
        self.assertEqual(self.ev.evaluate("π").display, repr(math.pi))


class ParenBalancingTest(unittest.TestCase):
    def test_missing_closers_are_added(self):
        self.assertEqual(balance_parens("sin(2"), ("sin(2)", True))
        self.assertEqual(balance_parens("((1+2"), ("((1+2))", True))

    def test_extra_closer_is_rejected(self):
        _, ok = balance_parens("1+2)")
        self.assertFalse(ok)

    def test_evaluating_unclosed_expression_works(self):
        self.assertEqual(Evaluator().evaluate("sqrt(16").display, "4.0")

    def test_extra_closer_reports_error(self):
        self.assertEqual(Evaluator().evaluate("1+2)").error, "右括号多了")


class PartialInputTest(unittest.TestCase):
    """边打边算：没打完的算式不该弹错误。"""

    def setUp(self):
        self.ev = Evaluator()

    def test_trailing_operator_is_incomplete(self):
        result = self.ev.evaluate("2+")
        self.assertTrue(result.incomplete)
        self.assertIsNone(result.error)
        self.assertEqual(result.display, "")

    def test_empty_input_shows_nothing(self):
        result = self.ev.evaluate("   ")
        self.assertEqual(result.display, "")
        self.assertIsNone(result.error)

    def test_bare_function_name_shows_nothing(self):
        self.assertEqual(self.ev.evaluate("tanh").display, "")

    def test_empty_call_is_waiting_for_arguments_not_broken(self):
        """点面板上的 sqrt() 按钮时，光标正停在括号里——别弹红字。"""
        for expr in ("sqrt()", "log()", "atan2()", "min()", "factorial()", "1+sqrt()"):
            with self.subTest(expr=expr):
                result = self.ev.evaluate(expr)
                self.assertTrue(result.incomplete)
                self.assertIsNone(result.error)
                self.assertEqual(result.display, "")

    def test_half_typed_name_is_not_yet_a_mistake(self):
        """手打 sqrt 的路上会经过 s / sq / sqr，一路飘红太吓人。"""
        for expr in ("s", "sq", "sqr", "xyz"):
            with self.subTest(expr=expr):
                result = self.ev.evaluate(expr)
                self.assertTrue(result.incomplete)
                self.assertIsNone(result.error)

    def test_a_typo_in_an_actual_call_still_reports(self):
        self.assertIn("nosuch", self.ev.evaluate("nosuch(2)").error)
        self.assertIsNotNone(self.ev.evaluate("2+nope").error)


class ErrorTest(unittest.TestCase):
    def setUp(self):
        self.ev = Evaluator()

    def test_division_by_zero(self):
        self.assertEqual(self.ev.evaluate("1/0").error, "除数不能为 0")

    def test_domain_error(self):
        self.assertEqual(self.ev.evaluate("log(-1)").error, "超出函数定义域")

    def test_unknown_name(self):
        self.assertIn("nosuch", self.ev.evaluate("nosuch(2)").error)

    def test_wrong_arity(self):
        self.assertIsNotNone(self.ev.evaluate("sin(1, 2)").error)


class SafetyTest(unittest.TestCase):
    """只算数，不执行任意代码。"""

    def setUp(self):
        self.ev = Evaluator()

    def test_import_is_blocked(self):
        self.assertIsNotNone(self.ev.evaluate('__import__("os")').error)

    def test_dunder_escape_is_blocked(self):
        self.assertIsNotNone(self.ev.evaluate("().__class__").error)

    def test_attribute_access_is_blocked(self):
        self.assertIsNotNone(self.ev.evaluate("pi.real").error)

    def test_open_is_not_available(self):
        self.assertIsNotNone(self.ev.evaluate('open("x")').error)

    def test_lambda_is_blocked(self):
        self.assertIsNotNone(self.ev.evaluate("(lambda: 1)()").error)

    def test_huge_power_is_blocked(self):
        self.assertIsNotNone(self.ev.evaluate("9**9**9").error)

    def test_huge_factorial_is_blocked(self):
        self.assertIsNotNone(self.ev.evaluate("factorial(10**9)").error)


class VariablesTest(unittest.TestCase):
    def setUp(self):
        self.ev = Evaluator()

    def test_assignment_then_use(self):
        result = self.ev.evaluate("x = 5")
        self.assertEqual(result.assigned, "x")
        self.assertEqual(result.display, "x = 5")
        self.assertEqual(self.ev.evaluate("x*2").display, "10")

    def test_augmented_assignment(self):
        self.ev.evaluate("n = 1")
        self.ev.evaluate("n += 4")
        self.assertEqual(self.ev.evaluate("n").display, "5")

    def test_ans_holds_last_committed_result(self):
        result = self.ev.evaluate("27*27")
        self.ev.commit(result)
        self.assertEqual(self.ev.evaluate("ans+1").display, "730")

    def test_reset_clears_variables(self):
        self.ev.evaluate("q = 3")
        self.assertEqual(self.ev.evaluate("q").display, "3")
        self.ev.reset()
        # 没定义的光杆名字算「还没打完」（见 still_typing），所以是没值、而非报错
        result = self.ev.evaluate("q")
        self.assertFalse(result.ok)
        self.assertEqual(result.display, "")


class ScriptTest(unittest.TestCase):
    """多行模式：逐行算、共用一个命名空间，show 决定哪些行把结果亮出来。"""

    def setUp(self):
        self.ev = Evaluator()

    def shown(self, text):
        """只取要显示的行，返回 [(算式, 显示文本)]。"""
        return [(line.source, line.result.display)
                for line in self.ev.evaluate_script(text) if line.shown]

    def test_lines_share_one_namespace(self):
        out = self.ev.evaluate_script("r = 3\nh = 10\nr*h")
        self.assertEqual(out[-1].result.display, "30")

    def test_only_the_last_line_shows_by_default(self):
        self.assertEqual(self.shown("r = 3\nh = 10\nr*h"), [("r*h", "30")])

    def test_show_lights_up_a_middle_line(self):
        self.assertEqual(self.shown("r = 3\nshow h = 10\nr*h"),
                         [("h = 10", "h = 10"), ("r*h", "30")])

    def test_show_also_works_on_a_bare_expression(self):
        self.assertEqual(self.shown("r = 3\nshow r*2\nr+1"),
                         [("r*2", "6"), ("r+1", "4")])

    def test_blank_lines_are_skipped(self):
        out = self.ev.evaluate_script("r = 3\n\n\nr*2")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[-1].result.display, "6")

    def test_a_trailing_newline_still_shows_the_last_real_line(self):
        self.assertEqual(self.shown("r = 3\nr*2\n"), [("r*2", "6")])

    def test_show_can_still_be_an_ordinary_variable_name(self):
        out = self.ev.evaluate_script("show = 5\nshow*2")
        self.assertEqual(out[-1].result.display, "10")

    def test_a_broken_line_does_not_stop_the_rest(self):
        out = self.ev.evaluate_script("a = 1\n1/0\nshow a+1")
        self.assertEqual(out[1].result.error, "除数不能为 0")
        self.assertEqual(out[2].result.display, "2")

    def test_a_failing_line_is_never_silent(self):
        """没写 show 也得把错说出来——出错还闷着才是最坑的。"""
        out = self.ev.evaluate_script("a = 1\nnosuch(2)\na+1")
        self.assertTrue(out[1].shown)
        self.assertIn("nosuch", out[1].result.error)

    def test_a_half_typed_line_stays_quiet(self):
        """但「还没打完」不算错，边打边算时不该一路飘红。"""
        out = self.ev.evaluate_script("a = 1\n2+\nsqr\na+1")
        self.assertFalse(out[1].shown)
        self.assertFalse(out[2].shown)

    def test_show_also_accepts_the_call_form(self):
        """面板上所有东西都长成 func()，用户会本能地写 show(x)。"""
        self.assertEqual(self.shown("a = 3\nb = a**2\nshow(b)\nb+1"),
                         [("(b)", "9"), ("b+1", "10")])

    def test_fancy_symbols_work_per_line(self):
        self.assertEqual(self.shown("show √16\n3²+4²"),
                         [("√16", "4.0"), ("3²+4²", "25")])

    def test_line_count_is_capped(self):
        out = self.ev.evaluate_script("\n".join(["1"] * 200))
        self.assertLessEqual(len(out), 40)

    def test_empty_script_produces_nothing(self):
        self.assertEqual(self.ev.evaluate_script("   \n\n  "), [])


class StripShowTest(unittest.TestCase):
    """show 是行首关键字，但不能把它变成保留字——用户拿它当变量名也得让路。"""

    def test_show_prefix_is_stripped(self):
        self.assertEqual(strip_show("show x"), ("x", True))
        self.assertEqual(strip_show("show x = 2"), ("x = 2", True))
        self.assertEqual(strip_show("  show  sqrt(2)"), ("sqrt(2)", True))

    def test_the_call_form_works_too(self):
        # 括号原样留着就行——(b) 求值等于 b
        self.assertEqual(strip_show("show(b)"), ("(b)", True))
        self.assertEqual(strip_show("show (b)"), ("(b)", True))
        self.assertEqual(strip_show("show(a*2+1)"), ("(a*2+1)", True))

    def test_a_line_without_show_is_untouched(self):
        self.assertEqual(strip_show("x = 2"), ("x = 2", False))
        self.assertEqual(strip_show("shower(1)"), ("shower(1)", False))
        self.assertEqual(strip_show("showx"), ("showx", False))

    def test_show_used_as_a_variable_is_left_alone(self):
        self.assertEqual(strip_show("show = 5"), ("show = 5", False))
        self.assertEqual(strip_show("show += 1"), ("show += 1", False))
        self.assertEqual(strip_show("show"), ("show", False))
        self.assertEqual(strip_show("show * 2"), ("show * 2", False))
        # 减号最阴险：'- 1' 单独看是合法表达式，但这里显然是「show 减一」
        self.assertEqual(strip_show("show - 1"), ("show - 1", False))
        self.assertEqual(strip_show("show ** 2"), ("show ** 2", False))


class FormattingTest(unittest.TestCase):
    def test_bool(self):
        self.assertEqual(format_value(True), "True")

    def test_int(self):
        self.assertEqual(format_value(729), "729")

    def test_float_shortest_roundtrip(self):
        self.assertEqual(format_value(0.1 + 0.2), "0.30000000000000004")

    def test_infinities_and_nan(self):
        self.assertEqual(format_value(math.inf), "inf")
        self.assertEqual(format_value(-math.inf), "-inf")
        self.assertEqual(format_value(math.nan), "nan")

    def test_callable_shows_nothing(self):
        self.assertEqual(format_value(math.tanh), "")

    def test_shorten_keeps_head_and_tail(self):
        text = "1234567890" * 40
        out = shorten(text, 50)
        self.assertEqual(len(out), 50)
        self.assertTrue(out.startswith("123"))
        self.assertTrue(out.endswith("890"))
        self.assertIn("…", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
