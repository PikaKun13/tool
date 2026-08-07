"""界面冒烟测试：真的建一个窗口，把交互路径走一遍再关掉。

会在屏幕上一闪而过，属正常现象。测试期间剪贴板和配置文件都被接管，不会动真的。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calcbar import winapi                      # noqa: E402
from calcbar.symbols import SECTIONS            # noqa: E402
from calcbar.ui import CalcBar                  # noqa: E402


class _Event:
    """假的鼠标事件：拉伸只看 x_root 和 widget。"""

    def __init__(self, x_root, y_root=0, widget=None):
        self.x_root, self.y_root, self.widget = x_root, y_root, widget


class UiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._real_clipboard = winapi.set_clipboard_text
        cls.copied = []
        winapi.set_clipboard_text = lambda text: cls.copied.append(text) or True
        CalcBar._save_config = lambda self: None       # 别写配置文件
        cls.app = CalcBar()
        cls.app.win_x, cls.app.win_y = 200, 200
        cls.app._apply_geometry()

    @classmethod
    def tearDownClass(cls):
        winapi.set_clipboard_text = cls._real_clipboard
        cls.app.root.destroy()

    def setUp(self):
        self.app = type(self).app
        self.app.set_text("")
        self.copied.clear()

    # -- 显示 -----------------------------------------------------------
    def test_result_follows_typing(self):
        self.app.set_text("27*27")
        self.assertEqual(self.app.result_text, "= 729")

    def test_placeholder_when_empty(self):
        self.app.set_text("")
        self.assertEqual(self.app.result_text, "")
        self.assertTrue(self.app.placeholder.winfo_manager())

    def test_incomplete_expression_shows_nothing(self):
        self.app.set_text("2+")
        self.assertEqual(self.app.result_text, "")

    def test_error_is_shown(self):
        self.app.set_text("1/0")
        self.assertEqual(self.app.result_text, "除数不能为 0")
        self.assertEqual(self.app.result.cget("fg"), self.app.palette.error)

    def test_result_sits_right_after_the_expression(self):
        self.app.set_text("2*3")
        self.app.root.update_idletasks()
        entry_right = self.app.entry.winfo_x() + self.app.entry.winfo_width()
        self.assertGreaterEqual(self.app.result.winfo_x(), entry_right)
        self.assertLess(self.app.result.winfo_x(), entry_right + self.app.px(20))

    def test_long_result_is_truncated_not_overflowing(self):
        self.app.set_text("factorial(100)")
        self.app.root.update_idletasks()
        right_edge = self.app.result.winfo_x() + self.app.result.winfo_width()
        self.assertLess(right_edge, self.app.px(self.app.metrics.bar_width))
        self.assertIn("…", self.app.result.cget("text"))       # 显示的是省略版
        self.assertNotIn("…", self.app.result_text)            # 复制的是完整值

    # -- 输入 -----------------------------------------------------------
    def test_chip_inserts_and_puts_caret_inside_parens(self):
        self.app.insert("sqrt()", 1)
        self.assertEqual(self.app.text(), "sqrt()")
        self.assertEqual(self.app.entry.index("insert"), 5)
        self.app.insert("16", 0)
        self.assertEqual(self.app.text(), "sqrt(16)")
        self.assertEqual(self.app.result_text, "= 4.0")

    def test_pasted_control_characters_are_scrubbed(self):
        self.app.set_text("1+\n2\t*\x1b3")        # 换行/制表变空格，Esc 字符丢掉
        self.assertEqual(self.app.text(), "1+ 2 *3")
        self.assertEqual(self.app.result_text, "= 7")

    def test_every_chip_inserts_something_valid(self):
        for section in SECTIONS:
            for item in section.items:
                self.app.set_text("")
                self.app.insert(item.insert, item.caret_back)
                self.assertEqual(self.app.text(), item.insert)
                self.assertLessEqual(item.caret_back, len(item.insert))

    # -- 动作 -----------------------------------------------------------
    def test_enter_copies_result_and_remembers_ans(self):
        self.app.set_text("27*27")
        self.app.commit()
        self.assertEqual(self.copied, ["729"])
        self.app.set_text("ans+1")
        self.assertEqual(self.app.result_text, "= 730")

    def test_enter_on_broken_expression_copies_nothing(self):
        self.app.set_text("1/0")
        self.app.commit()
        self.assertEqual(self.copied, [])

    def test_history_recall(self):
        self.app.history.clear()
        self.app.set_text("1+1")
        self.app.commit()
        self.app.set_text("2+2")
        self.app.commit()
        self.app.set_text("")
        self.app.history_index = len(self.app.history)
        self.app.recall(-1)
        self.assertEqual(self.app.text(), "2+2")
        self.app.recall(-1)
        self.assertEqual(self.app.text(), "1+1")
        self.app.recall(1)
        self.assertEqual(self.app.text(), "2+2")

    def test_escape_clears_before_quitting(self):
        self.app.set_text("123")
        self.app.escape()
        self.assertEqual(self.app.text(), "")

    def test_panel_toggles_window_height(self):
        was_open = self.app.panel_open
        collapsed = self.app.px(self.app.metrics.bar_height)
        if was_open:
            self.app.toggle_panel()
        self.app.root.update_idletasks()
        self.assertEqual(self.app.root.winfo_height(), collapsed)
        self.app.toggle_panel()
        self.app.root.update_idletasks()
        self.assertEqual(self.app.root.winfo_height(),
                         collapsed + self.app.panel_height)
        if not was_open:
            self.app.toggle_panel()

    def test_escape_closes_panel_first(self):
        if not self.app.panel_open:
            self.app.toggle_panel()
        self.app.set_text("5")
        self.app.escape()
        self.assertFalse(self.app.panel_open)
        self.assertEqual(self.app.text(), "5")

    # -- 窗口 -----------------------------------------------------------
    def test_window_has_no_frame_and_is_rounded(self):
        self.assertTrue(self.app.root.overrideredirect())
        self.assertTrue(self.app.hwnd)
        self.assertTrue(winapi.round_corners(self.app.hwnd))

    def test_topmost_can_be_turned_off_and_on(self):
        self.app.topmost.set(False)
        self.app._apply_topmost()
        self.assertFalse(self.app.root.attributes("-topmost"))
        self.app.topmost.set(True)
        self.app._apply_topmost()
        self.assertTrue(self.app.root.attributes("-topmost"))

    def test_right_click_menu_labels_match_their_actions(self):
        menu = self.app._menu
        self.assertEqual(menu.type(2), "command")          # _popup_menu 改的是这一项
        self.assertIn("面板", menu.entrycget(2, "label"))

    def test_scale_is_applied_to_geometry(self):
        expected = self.app.px(self.app.metrics.bar_width)
        self.app.root.update_idletasks()
        self.assertEqual(self.app.root.winfo_width(), expected)

    # -- 拉伸宽度 --------------------------------------------------------
    def restorable(self):
        """借来改尺寸，用完自动恢复出厂大小。"""
        self.addCleanup(self.app.reset_size)
        self.app.win_x, self.app.win_y = 300, 300
        self.app._apply_geometry()
        return self.app

    def test_only_the_two_edges_start_a_resize(self):
        app = self.restorable()
        self.assertEqual(app._edge_at(app.win_x), -1)
        self.assertEqual(app._edge_at(app.win_x + app.width_px - 1), 1)
        self.assertEqual(app._edge_at(app.win_x + app.width_px // 2), 0)

    def test_pressing_the_middle_drags_instead_of_resizing(self):
        app = self.restorable()
        app._press(_Event(app.win_x + app.width_px // 2, 320))
        self.assertIsNone(app._resize_origin)
        self.assertIsNotNone(app._drag_origin)
        app._release(_Event(0))

    def test_dragging_the_right_edge_widens_the_window(self):
        app = self.restorable()
        start, grip = app.bar_width, app.win_x + app.width_px - 1
        app._press(_Event(grip))
        self.assertIsNotNone(app._resize_origin)
        app._motion(_Event(grip + app.px(120)))
        app._release(_Event(0))
        self.assertAlmostEqual(app.bar_width, start + 120, delta=1)
        app.root.update_idletasks()
        self.assertEqual(app.root.winfo_width(), app.width_px)

    def test_dragging_the_left_edge_keeps_the_right_edge_still(self):
        app = self.restorable()
        right = app.win_x + app.width_px
        app._press(_Event(app.win_x))
        app._motion(_Event(app.win_x + app.px(100)))      # 往右拖 = 变窄
        app._release(_Event(0))
        self.assertLess(app.bar_width, app.metrics.bar_width)
        self.assertAlmostEqual(app.win_x + app.width_px, right, delta=1)

    def test_width_stops_at_the_minimum(self):
        app = self.restorable()
        grip = app.win_x + app.width_px - 1
        app._press(_Event(grip))
        app._motion(_Event(app.win_x - app.px(400)))      # 使劲往左拖
        app._release(_Event(0))
        self.assertEqual(app.bar_width, app.metrics.min_bar_width)

    def test_narrowing_reflows_the_panel_without_spilling_out(self):
        app = self.restorable()
        roomy = app.panel_height
        app.bar_width = app.metrics.min_bar_width
        app._resize_layout()
        self.assertGreater(app.panel_height, roomy)       # 换行多了，面板变高
        for _title, chips in app._panel_rows:
            for chip, chip_w in chips:
                self.assertLessEqual(int(chip.place_info()["x"]) + chip_w,
                                     app.width_px)

    def test_hint_is_truncated_instead_of_spilling_out(self):
        app = self.restorable()
        app.bar_width = app.metrics.min_bar_width
        app._resize_layout()
        room = app.width_px - app.px(app.metrics.panel_pad_x) * 2
        self.assertLessEqual(app.font_hint.measure(app.hint.cget("text")), room)

    def test_long_result_still_fits_after_narrowing(self):
        app = self.restorable()
        app.bar_width = app.metrics.min_bar_width
        app._resize_layout()
        app.set_text("factorial(100)")
        app.root.update_idletasks()
        self.assertLess(app.result.winfo_x() + app.result.winfo_width(),
                        app.width_px)

    # -- 整体缩放 --------------------------------------------------------
    def test_zoom_scales_fonts_and_window_together(self):
        app = self.restorable()
        font_before, width_before = app.font_input.cget("size"), app.width_px
        app.zoom_by(3)
        self.assertAlmostEqual(app.zoom, 1.3, places=2)
        self.assertLess(app.font_input.cget("size"), font_before)   # 负数字号
        self.assertGreater(app.width_px, width_before)
        app.root.update_idletasks()
        self.assertEqual(app.root.winfo_width(), app.width_px)

    def test_zoom_stops_at_both_limits(self):
        app = self.restorable()
        app.zoom_by(50)
        self.assertAlmostEqual(app.zoom, 2.0, places=2)
        app.zoom_by(-100)
        self.assertAlmostEqual(app.zoom, 0.7, places=2)

    def test_rebuild_after_zoom_keeps_the_expression_and_still_calculates(self):
        app = self.restorable()
        app.set_text("27*27")
        app.zoom_by(2)
        self.assertEqual(app.text(), "27*27")
        self.assertEqual(app.result_text, "= 729")
        app.set_text("2**5")                       # 新控件上的绑定还活着
        self.assertEqual(app.result_text, "= 32")

    def test_reset_size_restores_both_defaults(self):
        app = self.restorable()
        app.bar_width = 500
        app.zoom_by(2)
        app.reset_size()
        self.assertEqual(app.bar_width, app.metrics.bar_width)
        self.assertEqual(app.zoom, 1.0)

    # -- 多行模式 --------------------------------------------------------
    def in_multiline(self):
        """切到多行，测完自动切回单行并清干净。"""
        self.addCleanup(self._back_to_single)
        if not self.app.multiline:
            self.app.toggle_multiline()
        return self.app

    def _back_to_single(self):
        if self.app.multiline:
            self.app.toggle_multiline()
        self.app._drafts = {False: "", True: ""}
        self.app.set_text("")

    def shown_results(self):
        return [label.cget("text") for label in self.app._line_labels
                if label.winfo_manager()]

    def test_ctrl_m_switches_the_input_widget(self):
        app = self.in_multiline()
        self.assertTrue(app.multiline)
        self.assertEqual(app.entry.winfo_class(), "Text")
        app.toggle_multiline()
        self.assertFalse(app.multiline)
        self.assertEqual(app.entry.winfo_class(), "Entry")

    def test_each_mode_keeps_its_own_draft(self):
        app = self.app
        self.addCleanup(self._back_to_single)
        app.set_text("27*27")
        app.toggle_multiline()
        self.assertEqual(app.text(), "")               # 切过去是空白的
        app.set_text("a = 2\na*3")
        app.toggle_multiline()
        self.assertEqual(app.text(), "27*27")          # 单行草稿还在
        app.toggle_multiline()
        self.assertEqual(app.text(), "a = 2\na*3")     # 多行草稿也还在

    def test_newlines_survive_only_in_multiline(self):
        app = self.in_multiline()
        app.set_text("a = 2\na*3")
        self.assertEqual(app.text(), "a = 2\na*3")
        app.toggle_multiline()
        app.set_text("a = 2\na*3")
        self.assertEqual(app.text(), "a = 2 a*3")      # 单行里换行压成空格

    def test_lines_share_variables_and_only_the_last_shows(self):
        app = self.in_multiline()
        app.set_text("r = 3\nh = 10\nr*h")
        app.root.update_idletasks()
        self.assertEqual(self.shown_results(), ["= 30"])

    def test_show_lights_up_a_middle_line(self):
        app = self.in_multiline()
        app.set_text("show a = 2\nshow a*3\na*4")
        app.root.update_idletasks()
        # 赋值行只显示值，变量名就在左边摆着
        self.assertEqual(self.shown_results(), ["= 2", "= 6", "= 8"])

    def test_results_line_up_with_the_lines_they_belong_to(self):
        app = self.in_multiline()
        app.set_text("show a = 2\nshow a*3\na*4")
        app.root.update_idletasks()
        ys = [label.winfo_y() for label in app._line_labels
              if label.winfo_manager()]
        self.assertEqual(len(ys), 3)
        line_h = app.font_input.metrics("linespace")
        for upper, lower in zip(ys, ys[1:]):
            self.assertAlmostEqual(lower - upper, line_h, delta=2)

    def test_a_broken_line_shows_red_without_killing_the_rest(self):
        app = self.in_multiline()
        app.set_text("a = 1\nshow 1/0\nshow a+1")
        app.root.update_idletasks()
        self.assertEqual(self.shown_results(), ["除数不能为 0", "= 2"])
        reds = [label for label in app._line_labels
                if label.winfo_manager() and label.cget("fg") == app.palette.error]
        self.assertEqual(len(reds), 1)

    def test_window_grows_with_the_line_count(self):
        app = self.in_multiline()
        app.set_text("1")
        app.root.update_idletasks()
        one = app.root.winfo_height()
        app.set_text("1\n2\n3\n4")
        app.root.update_idletasks()
        four = app.root.winfo_height()
        line_h = app.font_input.metrics("linespace")
        self.assertAlmostEqual(four - one, line_h * 3, delta=2)

    def test_window_height_stops_growing_past_the_cap(self):
        app = self.in_multiline()
        app.set_text("\n".join("1" for _ in range(12)))
        app.root.update_idletasks()
        capped = app.root.winfo_height()
        app.set_text("\n".join("1" for _ in range(30)))
        app.root.update_idletasks()
        self.assertEqual(app.root.winfo_height(), capped)

    def test_ctrl_enter_copies_the_last_value(self):
        app = self.in_multiline()
        app.set_text("r = 3\nh = 10\nr*h")
        app.commit()
        self.assertEqual(self.copied, ["30"])
        app.set_text("ans+1")                          # commit 之后 ans 也更新了
        self.assertEqual(app.script[-1].result.display, "31")

    def test_multiline_history_is_kept_apart_from_single_line(self):
        app = self.in_multiline()
        app.history.clear()
        app.history_multi.clear()
        app.set_text("a = 2\na*3")
        app.commit()
        self.assertEqual(app.history_multi, ["a = 2\na*3"])
        self.assertEqual(app.history, [])              # 没污染单行历史
        app.set_text("")
        app.history_index = len(app.history_multi)
        app.recall(-1)
        self.assertEqual(app.text(), "a = 2\na*3")

    def test_placeholder_and_hint_follow_the_mode(self):
        app = self.in_multiline()
        self.assertIn("show", app.placeholder.cget("text"))
        self.assertIn("Ctrl+Enter", app._hint_default())
        app.toggle_multiline()
        self.assertIn("2**3", app.placeholder.cget("text"))
        self.assertNotIn("Ctrl+Enter", app._hint_default())

    # -- 真发按键：直接调方法证明不了绑定是对的 -----------------------------
    def press(self, sequence):
        self.app.entry.focus_force()
        self.app.root.update()
        self.app.entry.event_generate(sequence)
        self.app.root.update()

    def test_enter_really_copies_in_single_line_mode(self):
        self.app.set_text("6*7")
        self.press("<Return>")
        self.assertEqual(self.copied, ["42"])

    def test_enter_inserts_a_newline_in_multiline_instead_of_copying(self):
        app = self.in_multiline()
        app.set_text("a = 6")
        app.box.caret_to_end()
        self.press("<Return>")
        self.assertEqual(app.text(), "a = 6\n")
        self.assertEqual(self.copied, [])

    def test_ctrl_enter_really_copies_in_multiline(self):
        app = self.in_multiline()
        app.set_text("a = 6\na*7")
        self.press("<Control-Return>")
        self.assertEqual(self.copied, ["42"])

    def test_ctrl_k_opens_the_panel_without_eating_the_line(self):
        """Text 的类绑定里 Ctrl+K 是「删到行尾」，必须被我们拦下。"""
        app = self.in_multiline()
        app.set_text("a = 6\na*7")
        was_open = app.panel_open
        self.press("<Control-k>")
        self.assertNotEqual(app.panel_open, was_open)
        self.assertEqual(app.text(), "a = 6\na*7")
        app.toggle_panel()

    def test_junk_in_the_config_falls_back_to_defaults(self):
        app = self.app
        self.assertEqual(app._clamp_zoom("nonsense"), 1.0)
        self.assertEqual(app._clamp_zoom(99), 2.0)
        self.assertEqual(app._clamp_zoom(0.01), 0.7)
        self.assertEqual(app._clamp_width("nonsense"),
                         app._clamp_width(app.metrics.bar_width))
        self.assertEqual(app._clamp_width(10), app.metrics.min_bar_width)


if __name__ == "__main__":
    unittest.main(verbosity=2)
