"""CalcBar 的界面：一条 Spotlight 风格的算式输入条。

布局全部用 ``place`` 手工摆，因为要做到「结果紧跟在算式后面」这种效果：
输入框的宽度实时等于文字宽度，灰色的 ``= 结果`` 就贴在它右边。
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

from . import winapi
from .evaluator import EvalResult, Evaluator, LineResult, format_value, shorten
from .icons import available as icons_available, calculator, magnifier, rounded_chip
from .inputbox import InputBox
from .symbols import HINT, HINT_MULTI, SECTIONS, Item
from .theme import DARK, LIGHT, METRICS

_LATIN_FAMILIES = ("Segoe UI Variable Display", "Segoe UI", "Tahoma")
_CJK_FAMILIES = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI")
_HISTORY_LIMIT = 60
_MULTI_HISTORY_LIMIT = 20      # 多行历史存的是整块草稿，条数少一点

# Ctrl+滚轮的整体缩放倍率
_ZOOM_MIN, _ZOOM_MAX, _ZOOM_STEP = 0.7, 2.0, 0.1

# 多行模式最多显示这么多行，再多就在输入框里滚动
_MAX_VISIBLE_LINES = 12


def _app_dir() -> Path:
    """绿色版：配置就放在程序旁边，不往系统里写东西。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


class CalcBar:
    def __init__(self) -> None:
        winapi.enable_dpi_awareness()

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.title("CalcBar")

        self.hwnd = 0            # 窗口真正映射之后才有效，见 _finish_window
        self.scale = winapi.cursor_dpi_scale()
        self.palette = DARK if winapi.prefers_dark() else LIGHT
        self.metrics = METRICS

        self.evaluator = Evaluator()
        self.current: EvalResult | None = None
        self.result_text = ""
        self.result_color = self.palette.muted
        self._flash_after: str | None = None
        self._flash_text: str | None = None
        self._flash_color = self.palette.muted
        self._drag_origin: tuple[int, int] | None = None
        self._resize_origin: tuple[int, int, int, int] | None = None
        self.win_x = self.win_y = 0        # 真正的位置在 _place_window 里定

        self.config = self._load_config()
        self.history: list[str] = list(self.config.get("history", []))
        self.history_multi: list[str] = list(self.config.get("history_multi", []))
        self.history_index = len(self.history)
        self.panel_open = bool(self.config.get("panel_open", False))
        # 单行 / 多行各留各的草稿：切过去是空白的，切回来还在
        self.multiline = bool(self.config.get("multiline", False))
        self._drafts = {False: "", True: ""}
        self.script: list[LineResult] = []       # 多行模式下每行的结果
        self._line_labels: list[tk.Label] = []
        # 尺寸两个自由度：zoom 管字大小，bar_width 管一行能装多少字
        self.zoom = self._clamp_zoom(self.config.get("zoom", 1.0))
        self.bar_width = self._clamp_width(self.config.get("width", METRICS.bar_width))

        self.topmost = tk.BooleanVar(master=self.root,
                                     value=bool(self.config.get("topmost", True)))
        self._init_fonts()
        self._build()
        self._bind_global()
        self._apply_topmost()

        self._place_window()
        self.root.deiconify()
        self._finish_window()
        self.root.after(30, self._grab_focus)
        self._on_change()

    def _finish_window(self) -> None:
        """窗口映射之后才能拿到最终 HWND，再让 DWM 画圆角、抢焦点。"""
        self.root.update()
        self.hwnd = winapi.toplevel_hwnd(self.root)
        winapi.round_corners(self.hwnd)
        winapi.focus_window(self.hwnd)

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------
    def px(self, logical: float) -> int:
        """逻辑像素 -> 当前显示器的物理像素（显示器 DPI × 用户缩放）。"""
        return int(round(logical * self.scale * self.zoom))

    @property
    def width_px(self) -> int:
        """窗口当前的物理宽度。摆位置一律用它，不要再用 metrics.bar_width。"""
        return self.px(self.bar_width)

    def _clamp_zoom(self, value) -> float:
        try:
            value = round(float(value), 2)
        except (TypeError, ValueError):
            return 1.0
        return min(_ZOOM_MAX, max(_ZOOM_MIN, value))

    def _clamp_width(self, logical) -> int:
        """逻辑宽度夹在 [最小宽, 显示器工作区宽] 之间。"""
        try:
            logical = float(logical)
        except (TypeError, ValueError):
            logical = self.metrics.bar_width
        unit = self.scale * self.zoom
        widest = winapi.cursor_work_area()[2] / unit
        return int(round(min(max(logical, self.metrics.min_bar_width), widest)))

    def _pick_family(self, candidates: tuple[str, ...]) -> str:
        installed = {name.lower() for name in tkfont.families(self.root)}
        for name in candidates:
            if name.lower() in installed:
                return name
        return candidates[-1]

    def _init_fonts(self) -> None:
        m = self.metrics
        latin = self._pick_family(_LATIN_FAMILIES)
        cjk = self._pick_family(_CJK_FAMILIES)
        self._font("font_input", latin, m.font_input)
        self._font("font_result", cjk, m.font_result)
        self._font("font_chip", latin, m.font_chip)
        self._font("font_section", cjk, m.font_section)
        self._font("font_hint", cjk, m.font_hint)
        self._font("font_placeholder", cjk, m.font_result)

    def _font(self, attr: str, family: str, size: int) -> None:
        """建字体；已经有了就只改字号——缩放时会反复调到这里。

        负数字号 = 直接按像素，不受 tk 自己那套 DPI 换算影响。
        """
        existing = getattr(self, attr, None)
        if existing is None:
            setattr(self, attr, tkfont.Font(self.root, family=family,
                                            size=-self.px(size)))
        else:
            existing.configure(size=-self.px(size))

    def _load_config(self) -> dict:
        try:
            with open(_app_dir() / "calcbar.json", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_config(self) -> None:
        data = {
            "x": self.win_x, "y": self.win_y,
            "width": self.bar_width, "zoom": self.zoom,
            "panel_open": self.panel_open,
            "multiline": self.multiline,
            "topmost": bool(self.topmost.get()),
            "history": self.history[-_HISTORY_LIMIT:],
            "history_multi": self.history_multi[-_MULTI_HISTORY_LIMIT:],
        }
        try:
            with open(_app_dir() / "calcbar.json", "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=1)
        except OSError:
            pass                                   # 只读目录也照样能用

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """从零搭出整个界面。缩放时会整个重来一遍，所以必须可重入。"""
        p, m = self.palette, self.metrics
        self.root.configure(bg=p.bg)

        self.outer = tk.Frame(self.root, bg=p.bg)
        self.outer.pack(fill="both", expand=True)

        self.bar = tk.Frame(self.outer, bg=p.bg, height=self._bar_height())
        self.bar.pack(fill="x")
        self.bar.pack_propagate(False)

        self._build_search_icon()
        self._build_entry()
        self._build_button()
        self._build_panel()
        self._bind_widgets()

        if self.panel_open:
            self.panel.pack(fill="both", expand=True)

    def _build_search_icon(self) -> None:
        p, m = self.palette, self.metrics
        size = self.px(m.icon_size)
        y = (self.px(m.bar_height) - size) // 2
        if icons_available():
            self._icon_image = tk.PhotoImage(
                master=self.root, data=magnifier(size, p.bg, p.icon))
            self.icon = tk.Label(self.bar, image=self._icon_image, bg=p.bg, bd=0)
        else:
            self.icon = tk.Canvas(self.bar, width=size, height=size, bg=p.bg,
                                  bd=0, highlightthickness=0)
            r = size * 0.30
            cx = cy = size * 0.40
            self.icon.create_oval(cx - r, cy - r, cx + r, cy + r,
                                  outline=p.icon, width=max(1, self.px(2)))
            self.icon.create_line(cx + r * 0.72, cy + r * 0.72, size * 0.9, size * 0.9,
                                  fill=p.icon, width=max(1, self.px(2)))
        self.icon.place(x=self.px(m.icon_x), y=y, width=size, height=size)

    def _build_entry(self) -> None:
        p = self.palette
        self.box = InputBox(
            self.bar, self.multiline, self._on_change, font=self.font_input,
            bg=p.bg, fg=p.fg, insertbackground=p.fg, bd=0, relief="flat",
            highlightthickness=0, exportselection=False,
            selectbackground=p.select_bg, selectforeground=p.select_fg,
            insertwidth=max(1, self.px(2)),
        )
        self.entry = self.box.widget          # 摆位置和绑事件时用得着

        flat = dict(bd=0, padx=0, pady=0, highlightthickness=0, anchor="w")
        self.placeholder = tk.Label(
            self.bar, bg=p.bg, fg=p.placeholder, font=self.font_placeholder,
            text=("每行一步，行首写 show 显示中间结果" if self.multiline
                  else "输入算式，比如  2**3  或  tanh(2)"),
            **flat)
        self.result = tk.Label(self.bar, text="", bg=p.bg, fg=p.muted,
                               font=self.font_result, **flat)
        # 多行模式下每个显示行配一个结果标签，够用就行，多的藏起来
        self._line_labels = [
            tk.Label(self.bar, text="", bg=p.bg, fg=p.muted,
                     font=self.font_result, **flat)
            for _ in range(_MAX_VISIBLE_LINES)] if self.multiline else []

    def _build_button(self) -> None:
        p, m = self.palette, self.metrics
        size = self.px(m.button_size)

        if icons_available():
            self._btn_normal = tk.PhotoImage(
                master=self.root,
                data=calculator(size, p.bg, p.button_bg, p.fg, p.bg))
            self._btn_hover = tk.PhotoImage(
                master=self.root,
                data=calculator(size, p.bg, p.button_hover, p.fg, p.bg))
            self.button = tk.Label(self.bar, image=self._btn_normal, bg=p.bg, bd=0)
            self.button.bind("<Enter>", lambda _: self.button.config(image=self._btn_hover))
            self.button.bind("<Leave>", lambda _: self.button.config(image=self._btn_normal))
        else:
            self.button = tk.Canvas(self.bar, width=size, height=size, bg=p.button_bg,
                                    bd=0, highlightthickness=0)
            pad = size * 0.24
            self.button.create_rectangle(pad, pad * 0.9, size - pad, size - pad * 0.9,
                                         fill=p.fg, outline="")
            self.button.bind("<Enter>", lambda _: self.button.config(bg=p.button_hover))
            self.button.bind("<Leave>", lambda _: self.button.config(bg=p.button_bg))

        self.button.configure(cursor="hand2")
        self.button.bind("<Button-1>", lambda _: self.toggle_panel())
        self._place_button()

    def _place_button(self) -> None:
        """按钮永远贴着右边缘——窗口一变宽就得重摆。"""
        m = self.metrics
        size = self.px(m.button_size)
        self.button.place(x=self.width_px - self.px(m.button_margin) - size,
                          y=(self.px(m.bar_height) - size) // 2,
                          width=size, height=size)

    # -- 符号面板 --------------------------------------------------------
    def _build_panel(self) -> None:
        """只负责造控件；摆在哪儿由 _layout_panel 按当前宽度决定。"""
        p, m = self.palette, self.metrics
        self.panel = tk.Frame(self.outer, bg=p.bg)
        self._chip_images: dict[tuple[int, int, str], tk.PhotoImage] = {}
        self._hint_text = self._hint_default()

        self.separator = tk.Frame(self.panel, bg=p.separator)
        chip_h = self.px(m.chip_h)
        self._panel_rows: list[tuple[tk.Label, list[tuple[tk.Label, int]]]] = []
        for section in SECTIONS:
            title = tk.Label(self.panel, text=section.title, bg=p.bg,
                             fg=p.section_fg, font=self.font_section, anchor="w")
            title.bind("<Button-1>", self._start_drag)
            title.bind("<B1-Motion>", self._on_drag)

            chips = []
            for item in section.items:
                chip_w = self.font_chip.measure(item.label) + self.px(m.chip_pad_x) * 2
                chips.append((self._make_chip(item, chip_w, chip_h), chip_w))
            self._panel_rows.append((title, chips))

        self.hint = tk.Label(self.panel, bg=p.bg, fg=p.hint,
                             font=self.font_hint, anchor="w")
        self.hint.bind("<Button-1>", self._start_drag)
        self.hint.bind("<B1-Motion>", self._on_drag)
        self._layout_panel()

    def _layout_panel(self) -> None:
        """按当前窗口宽度重排面板：装不下的 chip 换行，顺带算出 panel_height。"""
        m = self.metrics
        pad_x = self.px(m.panel_pad_x)
        avail = max(self.px(60), self.width_px - pad_x * 2)
        chip_h = self.px(m.chip_h)

        self.separator.place(x=pad_x, y=0, width=avail, height=max(1, self.px(1)))

        y = self.px(m.panel_pad_y)
        for title, chips in self._panel_rows:
            title.place(x=pad_x, y=y)
            y += self.font_section.metrics("linespace") + self.px(5)

            x = pad_x
            for chip, chip_w in chips:
                if x > pad_x and x + chip_w > pad_x + avail:
                    x = pad_x
                    y += chip_h + self.px(m.row_gap)
                chip.place(x=x, y=y, width=chip_w, height=chip_h)
                x += chip_w + self.px(m.chip_gap)
            y += chip_h + self.px(m.section_gap)

        self.hint.place(x=pad_x, y=y)
        self._set_hint(self._hint_text)
        self.panel_height = y + self.font_hint.metrics("linespace") + self.px(m.panel_pad_y)

    def _hint_default(self) -> str:
        """没悬停在任何按钮上时，底部显示的那行快捷键——两种模式不一样。"""
        return HINT_MULTI if self.multiline else HINT

    def _set_hint(self, text: str) -> None:
        """面板底部那行字。窗口拖窄之后要截断，免得糊到窗口外面去。"""
        self._hint_text = text
        room = self.width_px - self.px(self.metrics.panel_pad_x) * 2
        self.hint.configure(text=self._fit(text, self.font_hint, room))

    def _chip_image(self, width: int, height: int, fill: str) -> tk.PhotoImage:
        key = (width, height, fill)
        if key not in self._chip_images:
            self._chip_images[key] = tk.PhotoImage(
                master=self.root,
                data=rounded_chip(width, height, self.palette.bg, fill))
        return self._chip_images[key]

    def _make_chip(self, item: Item, width: int, height: int) -> tk.Label:
        p = self.palette
        tip = f"{item.label}　{item.tip}" if item.tip else item.label
        common = dict(text=item.label, fg=p.chip_fg, font=self.font_chip,
                      bd=0, highlightthickness=0, cursor="hand2")

        if icons_available():
            normal = self._chip_image(width, height, p.chip_bg)
            hover = self._chip_image(width, height, p.chip_hover)
            chip = tk.Label(self.panel, image=normal, compound="center",
                            bg=p.bg, **common)
            enter = lambda _: (chip.config(image=hover), self._set_hint(tip))
            leave = lambda _: (chip.config(image=normal),
                               self._set_hint(self._hint_default()))
        else:
            chip = tk.Label(self.panel, bg=p.chip_bg, **common)
            enter = lambda _: (chip.config(bg=p.chip_hover), self._set_hint(tip))
            leave = lambda _: (chip.config(bg=p.chip_bg),
                               self._set_hint(self._hint_default()))

        chip.bind("<Enter>", enter)
        chip.bind("<Leave>", leave)
        chip.bind("<Button-1>", lambda _: self.insert(item.insert, item.caret_back))
        return chip

    # ------------------------------------------------------------------
    # 事件绑定
    # ------------------------------------------------------------------
    def _bind_widgets(self) -> None:
        """挂在控件上的事件。缩放会重建控件，所以这些要跟着重挂。"""
        self.entry.bind("<Escape>", lambda _: (self.escape(), "break")[1])
        self.entry.bind("<Control-a>", self._select_all)
        self.entry.bind("<Control-c>", self._copy)
        # Text 类绑定里 Ctrl+K 是「删到行尾」，得在控件这一层拦掉
        self.entry.bind("<Control-k>", lambda _: (self.toggle_panel(), "break")[1])
        self.entry.bind("<Control-m>", lambda _: self.toggle_multiline())
        if self.multiline:
            # Enter 换行交给 Text 自己，复制让位给 Ctrl+Enter；
            # ↑↓ 得留给光标移动，翻历史挪到 Ctrl+↑↓
            self.entry.bind("<Control-Return>", lambda _: self.commit())
            self.entry.bind("<Control-KP_Enter>", lambda _: self.commit())
            self.entry.bind("<Control-Up>", lambda _: self.recall(-1))
            self.entry.bind("<Control-Down>", lambda _: self.recall(1))
        else:
            self.entry.bind("<Return>", lambda _: self.commit())
            self.entry.bind("<KP_Enter>", lambda _: self.commit())
            self.entry.bind("<Up>", lambda _: self.recall(-1))
            self.entry.bind("<Down>", lambda _: self.recall(1))

        for widget in (self.icon, self.placeholder, self.result):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)
        # bar 和 panel 是铺满整宽的，左右边缘那两条要让给拉伸
        for widget in (self.bar, self.panel):
            widget.bind("<Motion>", self._hover_edge)
            widget.bind("<Leave>", lambda _, w=widget: w.configure(cursor=""))
            widget.bind("<Button-1>", self._press)
            widget.bind("<B1-Motion>", self._motion)
            widget.bind("<ButtonRelease-1>", self._release)
        for widget in (self.bar, self.icon, self.placeholder, self.result,
                       self.panel, self.entry):
            widget.bind("<Button-3>", self._popup_menu)

    def _bind_global(self) -> None:
        """挂在 root 上的快捷键和右键菜单，整个进程只挂一次。"""
        self.root.bind("<Control-k>", lambda _: self.toggle_panel())
        self.root.bind("<Escape>", lambda _: self.escape())
        self.root.bind("<Control-MouseWheel>",
                       lambda e: self.zoom_by(1 if e.delta > 0 else -1))
        self.root.bind("<Control-equal>", lambda _: self.zoom_by(1))
        self.root.bind("<Control-plus>", lambda _: self.zoom_by(1))
        self.root.bind("<Control-minus>", lambda _: self.zoom_by(-1))
        self.root.bind("<Control-0>", lambda _: self.reset_size())
        self.root.bind("<Control-m>", lambda _: self.toggle_multiline())

        self.multiline_var = tk.BooleanVar(master=self.root, value=self.multiline)
        self._menu = tk.Menu(self.root, tearoff=0)
        self._menu.add_command(label="复制结果　Enter", command=self.commit)
        self._menu.add_command(label="清空", command=lambda: self.set_text(""))
        self._menu.add_command(label="符号面板　Ctrl+K", command=self.toggle_panel)
        self._menu.add_command(label="恢复默认大小　Ctrl+0", command=self.reset_size)
        self._menu.add_separator()
        self._menu.add_checkbutton(label="多行模式　Ctrl+M", variable=self.multiline_var,
                                   command=self.toggle_multiline)
        self._menu.add_checkbutton(label="总在最前", variable=self.topmost,
                                   command=self._apply_topmost)
        self._menu.add_command(label="清除自定义变量", command=self._reset_vars)
        self._menu.add_separator()
        self._menu.add_command(label="退出　Esc", command=self.quit)

    def _popup_menu(self, event) -> None:
        self._menu.entryconfigure(0, label="复制结果　Ctrl+Enter" if self.multiline
                                  else "复制结果　Enter")
        self._menu.entryconfigure(2, label="收起面板　Ctrl+K" if self.panel_open
                                  else "符号面板　Ctrl+K")
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _grab_focus(self) -> None:
        try:
            self.root.focus_force()
            self.box.focus()
        except tk.TclError:
            pass

    def _select_all(self, _event=None) -> str:
        self.box.select_all()
        return "break"

    def _copy(self, _event=None) -> str:
        selected = self.box.selected_text()
        if selected:
            winapi.set_clipboard_text(selected)
        else:
            self.commit()
        return "break"

    def _apply_topmost(self) -> None:
        self.root.attributes("-topmost", bool(self.topmost.get()))

    def _reset_vars(self) -> None:
        self.evaluator.reset()
        self._on_change()
        self._flash("已清除自定义变量")

    # -- 拖动 -----------------------------------------------------------
    def _start_drag(self, event) -> None:
        self._drag_origin = (event.x_root - self.win_x, event.y_root - self.win_y)

    def _on_drag(self, event) -> None:
        if self._drag_origin is None:
            return
        self.win_x = event.x_root - self._drag_origin[0]
        self.win_y = event.y_root - self._drag_origin[1]
        self._apply_geometry()

    # -- 拉伸宽度 --------------------------------------------------------
    def _edge_at(self, x_root: int) -> int:
        """鼠标压在窗口左/右边缘上就返回 -1 / +1，在中间返回 0。"""
        offset = x_root - self.win_x
        edge = max(3, self.px(self.metrics.resize_edge))
        if offset < edge:
            return -1
        if offset > self.width_px - edge:
            return 1
        return 0

    def _hover_edge(self, event) -> None:
        """边缘上把光标换成 ↔，这是「这里能拉」的唯一提示。"""
        event.widget.configure(
            cursor="sb_h_double_arrow" if self._edge_at(event.x_root) else "")

    def _press(self, event) -> None:
        side = self._edge_at(event.x_root)
        if side:
            self._resize_origin = (side, event.x_root, self.bar_width, self.win_x)
        else:
            self._start_drag(event)

    def _motion(self, event) -> None:
        if self._resize_origin is None:
            self._on_drag(event)
            return
        side, x0, width0, win_x0 = self._resize_origin
        unit = self.scale * self.zoom
        self.bar_width = self._clamp_width(width0 + (event.x_root - x0) / unit * side)
        if side < 0:                      # 拖左边缘时右边界钉住不动
            self.win_x = win_x0 + int(round((width0 - self.bar_width) * unit))
        self._resize_layout()

    def _release(self, _event) -> None:
        self._resize_origin = None
        self._drag_origin = None

    def _resize_layout(self) -> None:
        """宽度变了：重摆按钮和面板即可，一个控件都不用重建。"""
        self._place_button()
        self._layout_panel()
        self._relayout()
        self._apply_geometry()

    # -- 整体缩放 --------------------------------------------------------
    def zoom_by(self, steps: int) -> str:
        target = self._clamp_zoom(self.zoom + _ZOOM_STEP * steps)
        if target != self.zoom:
            self._apply_zoom(target)
        return "break"

    def reset_size(self) -> str:
        """宽度和倍率都回出厂值——设置是存盘的，得留个逃生口。"""
        self.bar_width = self._clamp_width(self.metrics.bar_width)
        if self.zoom != 1.0:
            self._apply_zoom(1.0)
        else:
            self._resize_layout()
        self._flash("已恢复默认大小")
        return "break"

    def _apply_zoom(self, zoom: float) -> None:
        """倍率一变，字号和图标的像素尺寸全得重算，只能整个界面重建一次。"""
        text, caret = self.box.text(), self.box.caret()
        self.zoom = zoom
        self.bar_width = self._clamp_width(self.bar_width)
        self._init_fonts()
        self._rebuild(text, caret)

        area_x, _, area_w, _ = winapi.cursor_work_area()
        self.win_x = max(area_x, min(self.win_x, area_x + area_w - self.width_px))
        self._apply_geometry()

    # ------------------------------------------------------------------
    # 窗口位置与大小
    # ------------------------------------------------------------------
    def _place_window(self) -> None:
        width = self.width_px
        area_x, area_y, area_w, area_h = winapi.cursor_work_area()

        self.win_x = self.config.get("x")
        self.win_y = self.config.get("y")
        if not isinstance(self.win_x, int) or not isinstance(self.win_y, int):
            self.win_x = area_x + (area_w - width) // 2
            self.win_y = area_y + int(area_h * 0.22)
        # 上次的显示器可能已经拔了，拉回可见区域
        self.win_x = max(area_x, min(self.win_x, area_x + area_w - width))
        self.win_y = max(area_y, min(self.win_y, area_y + area_h - self.px(80)))
        self._apply_geometry()

    def _apply_geometry(self) -> None:
        width = self.width_px
        height = self._bar_height()
        if self.panel_open:
            height += self.panel_height
        self.root.geometry(f"{width}x{height}+{int(self.win_x)}+{int(self.win_y)}")

    def toggle_panel(self) -> None:
        self.panel_open = not self.panel_open
        if self.panel_open:
            self.panel.pack(fill="both", expand=True)
        else:
            self.panel.pack_forget()
        self._apply_geometry()
        self.box.focus()

    # ------------------------------------------------------------------
    # 输入 -> 计算 -> 排版
    # ------------------------------------------------------------------
    def insert(self, text: str, caret_back: int = 0) -> None:
        self.box.insert(text, caret_back)

    def set_text(self, text: str) -> None:
        self.box.set_text(text)
        self.box.caret_to_end()

    def text(self) -> str:
        return self.box.text()

    def _sanitize(self, text: str) -> str:
        """控制字符直接扔掉。单行模式下换行也压成空格，多行模式下留着。"""
        out = []
        for ch in text:
            if ch == "\n" and self.multiline:
                out.append(ch)
            elif ch in "\t\n\r":
                out.append(" ")
            elif ch >= " " and ch != "\x7f":
                out.append(ch)
        return "".join(out)

    def _describe(self, result: EvalResult, source: str,
                  bare: bool = False) -> tuple[str, str]:
        """一次求值 -> (显示什么字, 什么颜色)。单行和多行共用这套判断。

        ``bare`` 给多行用：赋值行只显示值，因为变量名就在同一行左边摆着，
        再写成「= v = 282.7」纯属重复。
        """
        p = self.palette
        if not source.strip():
            return "", p.muted
        if result.error and not result.incomplete:
            return result.error, p.error
        if result.display:
            display = (format_value(result.value)
                       if bare and result.assigned else result.display)
            shown = "= " + shorten(display)
            if result.note:
                shown += f"　（{result.note}）"
            return shown, p.muted
        return "", p.muted

    def _on_change(self) -> None:
        raw = self.box.text()
        text = self._sanitize(raw)
        if text != raw:
            self.box.set_text(text, notify=False)   # 别再绕回自己

        if self.multiline:
            self.script = self.evaluator.evaluate_script(text)
            self.current = self.script[-1].result if self.script else None
            self.result_text, self.result_color = "", self.palette.muted
        else:
            self.script = []
            self.current = self.evaluator.evaluate(text)
            self.result_text, self.result_color = self._describe(self.current, text)
        self._cancel_flash()
        self._relayout()

    def _bar_height(self) -> int:
        """单行是固定高；多行按行数长，到 _MAX_VISIBLE_LINES 封顶后改为滚动。"""
        base = self.px(self.metrics.bar_height)
        if not self.multiline:
            return base
        line_h = self.font_input.metrics("linespace")
        pad = max(0, (base - line_h) // 2)
        box = getattr(self, "box", None)
        rows = box.line_count() if box is not None else 1
        return min(rows, _MAX_VISIBLE_LINES) * line_h + pad * 2

    def _right_edge(self) -> int:
        """算式区能用到的最右边（再往右是那个计算器按钮）。"""
        m = self.metrics
        return (self.width_px - self.px(m.button_margin)
                - self.px(m.button_size) - self.px(12))

    def _relayout(self) -> None:
        if self.multiline:
            self._relayout_script()
        else:
            self._relayout_single()
        self.bar.configure(height=self._bar_height())
        self._apply_geometry()

    def _relayout_script(self) -> None:
        """多行：输入区占左边，结果排成一列贴在右边，逐行对齐。"""
        m = self.metrics
        text_x, gap = self.px(m.text_x), self.px(m.result_gap)
        right = self._right_edge()
        span = max(self.px(80), right - text_x)
        line_h = self.font_input.metrics("linespace")
        pad_y = max(0, (self.px(m.bar_height) - line_h) // 2)

        # 结果列的位置：够放下最长的一行，再夹在 30%~60% 之间，免得打字时乱跳
        longest = max((self.font_input.measure(line) for line in self.box.lines()),
                      default=0)
        col = int(min(max(longest + gap, span * 0.30), span * 0.60))
        rows = min(self.box.line_count(), _MAX_VISIBLE_LINES)
        self.entry.place(x=text_x, y=pad_y, width=max(self.px(40), col - gap),
                         height=rows * line_h)

        if self.box.text():
            self.placeholder.place_forget()
        else:
            self.placeholder.place(
                x=text_x + self.px(2),
                y=pad_y + self.font_input.metrics("ascent")
                - self.font_placeholder.metrics("ascent"))
        self.result.place_forget()

        wanted: list[list] = []
        for line in self.script:
            if not line.shown:
                continue
            shown, color = self._describe(line.result, line.source, bare=True)
            if shown:
                wanted.append([line.index, shown, color])
        if self._flash_text is not None:
            if wanted:
                wanted[-1][1:] = [self._flash_text, self._flash_color]
            else:
                wanted.append([0, self._flash_text, self._flash_color])

        self.root.update_idletasks()          # dlineinfo 得等布局落地才准
        room = max(self.px(40), right - text_x - col)
        used = 0
        for index, shown, color in wanted:
            if used >= len(self._line_labels):
                break
            where = self.box.line_metrics(index)
            if where is None:
                continue                       # 这行滚出视野了
            top, baseline = where
            label = self._line_labels[used]
            used += 1
            label.configure(text=self._fit(shown, self.font_result, room), fg=color)
            label.place(x=text_x + col,
                        y=pad_y + top + baseline - self.font_result.metrics("ascent"))
        for label in self._line_labels[used:]:
            label.place_forget()

    def _relayout_single(self) -> None:
        m = self.metrics
        bar_h = self.px(m.bar_height)
        text_x = self.px(m.text_x)
        gap = self.px(m.result_gap)
        right = self._right_edge()

        entry_h = self.font_input.metrics("linespace")
        entry_y = (bar_h - entry_h) // 2
        base = entry_y + self.font_input.metrics("ascent")

        text = self.box.text()
        if not text:
            self.placeholder.place(x=text_x + self.px(2),
                                   y=base - self.font_placeholder.metrics("ascent"))
        else:
            self.placeholder.place_forget()

        result_text = self._flash_text if self._flash_text is not None else self.result_text
        color = self._flash_color if self._flash_text is not None else self.result_color
        if result_text:
            room = int((right - text_x) * 0.55)       # 算式至少留 45% 的位置
            result_text = self._fit(result_text, self.font_result, room)
        result_w = self.font_result.measure(result_text) if result_text else 0

        max_entry = right - text_x - (result_w + gap if result_text else 0)
        max_entry = max(self.px(40), max_entry)
        entry_w = max(self.px(8), min(self.font_input.measure(text) + self.px(4),
                                      max_entry))
        self.entry.place(x=text_x, y=entry_y, width=entry_w, height=entry_h)

        if result_text:
            self.result.configure(text=result_text, fg=color)
            self.result.place(x=text_x + entry_w + gap,
                              y=base - self.font_result.metrics("ascent"))
        else:
            self.result.place_forget()

    @staticmethod
    def _fit(text: str, font: tkfont.Font, max_width: int) -> str:
        """结果太长就中间省略，保证不会撞到右边的按钮。"""
        if max_width <= 0 or font.measure(text) <= max_width:
            return text
        low, high = 4, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if font.measure(shorten(text, mid)) <= max_width:
                low = mid
            else:
                high = mid - 1
        return shorten(text, low)

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------
    def commit(self) -> str:
        if self.multiline:
            self._commit_script()
            return "break"
        result = self.current
        if result is None:
            return "break"
        if not result.ok or not result.display:
            self._flash(result.error or "算式还没写完", error=True)
            return "break"
        self.evaluator.commit(result)
        winapi.set_clipboard_text(format_value(result.value))
        expression = self.box.text().strip()
        if expression and (not self.history or self.history[-1] != expression):
            self.history.append(expression)
            del self.history[:-_HISTORY_LIMIT]
        self.history_index = len(self.history)
        self._select_all()
        self._flash("已复制到剪贴板")
        return "break"

    def _commit_script(self) -> None:
        """多行：复制最后一个显示行的值，整块草稿进多行历史。"""
        last = next((line for line in reversed(self.script)
                     if line.shown and line.result.ok and line.result.display), None)
        if last is None:
            self._flash("还没有能复制的结果", error=True)
            return
        self.evaluator.commit(last.result)
        winapi.set_clipboard_text(format_value(last.result.value))
        block = self.box.text().strip()
        if block and (not self.history_multi or self.history_multi[-1] != block):
            self.history_multi.append(block)
            del self.history_multi[:-_MULTI_HISTORY_LIMIT]
        self.history_index = len(self.history_multi)
        self._flash("已复制到剪贴板")

    def recall(self, step: int) -> str:
        history = self.history_multi if self.multiline else self.history
        if not history:
            return "break"
        index = self.history_index + step
        if index < 0:
            index = 0
        if index >= len(history):
            self.history_index = len(history)
            self.set_text("")
            return "break"
        self.history_index = index
        self.set_text(history[index])
        return "break"

    def escape(self) -> None:
        if self.panel_open:
            self.toggle_panel()
        elif self.box.text():
            self.set_text("")
        else:
            self.quit()

    # -- 单行 / 多行 ------------------------------------------------------
    def toggle_multiline(self) -> str:
        """两种模式各留各的草稿：切过去是空白的，切回来还在。"""
        self._drafts[self.multiline] = self.box.text()
        self.multiline = not self.multiline
        self.multiline_var.set(self.multiline)
        self._rebuild(self._drafts[self.multiline])
        history = self.history_multi if self.multiline else self.history
        self.history_index = len(history)
        self._flash("多行模式：每行一步，行首 show 显示中间结果" if self.multiline
                    else "单行模式")
        return "break"

    def _rebuild(self, text: str, caret: str | None = None) -> None:
        """控件类型或字号变了，只能把界面整个重搭一次。"""
        self.outer.destroy()
        self._build()
        self.box.set_text(text, notify=False)
        if caret:
            self.box.restore_caret(caret)
        else:
            self.box.caret_to_end()
        self.box.focus()
        self._on_change()
        self._apply_geometry()

    def quit(self) -> None:
        self._save_config()
        self.root.destroy()

    # -- 短暂提示（“已复制”之类，1 秒后自动变回结果） -----------------------
    def _cancel_flash(self) -> None:
        if self._flash_after is not None:
            self.root.after_cancel(self._flash_after)
            self._flash_after = None
        self._flash_text = None

    def _flash(self, message: str, error: bool = False) -> None:
        self._cancel_flash()
        self._flash_text = message
        self._flash_color = self.palette.error if error else self.palette.muted
        self._relayout()
        self._flash_after = self.root.after(1100, self._restore_after_flash)

    def _restore_after_flash(self) -> None:
        self._flash_after = None
        self._flash_text = None
        self._relayout()

    # ------------------------------------------------------------------
    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    CalcBar().run()
