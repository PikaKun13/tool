"""CalcBar の画面：Spotlight 風の式入力バー。

レイアウトはすべて ``place`` で手作業で配置する。「結果が式のすぐ後ろに続く」見た目にするため：
入力欄の幅を常に文字の幅と同じにし、グレーの ``= 結果`` をそのすぐ右に置く。
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
_MULTI_HISTORY_LIMIT = 20      # 複数行の履歴は下書きのブロック全体を保存するので、件数は少なめ

# Ctrl+ホイールによる全体の拡大率
_ZOOM_MIN, _ZOOM_MAX, _ZOOM_STEP = 0.7, 2.0, 0.1

# 複数行モードで表示する最大行数。それより多ければ入力欄の中でスクロールする
_MAX_VISIBLE_LINES = 12


def _app_dir() -> Path:
    """ポータブル版：設定はプログラムの横に置き、システムには何も書き込まない。"""
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

        self.hwnd = 0            # ウィンドウが実際にマップされてから有効になる。_finish_window を参照
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
        self.win_x = self.win_y = 0        # 実際の位置は _place_window で決める

        self.config = self._load_config()
        self.history: list[str] = list(self.config.get("history", []))
        self.history_multi: list[str] = list(self.config.get("history_multi", []))
        self.history_index = len(self.history)
        self.panel_open = bool(self.config.get("panel_open", False))
        # 1 行 / 複数行はそれぞれ別の下書きを持つ：切り替えた先は空で、戻ると残っている
        self.multiline = bool(self.config.get("multiline", False))
        self._drafts = {False: "", True: ""}
        self.script: list[LineResult] = []       # 複数行モードでの各行の結果
        self._line_labels: list[tk.Label] = []
        # 結果列のレイアウト。スクロール時はこれを元に貼り直す。_place_result_labels を参照
        self._result_rows: list[list] = []
        self._result_col = self._result_room = self._result_pad_y = 0
        self._scroll_pending = False
        # サイズの自由度は 2 つ：zoom は文字の大きさ、bar_width は 1 行に入る文字数を決める
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
        """ウィンドウがマップされて初めて最終的な HWND が取れるので、そこで DWM に角丸を描かせ、フォーカスを取る。"""
        self.root.update()
        self.hwnd = winapi.toplevel_hwnd(self.root)
        winapi.round_corners(self.hwnd)
        winapi.focus_window(self.hwnd)

    # ------------------------------------------------------------------
    # 基盤
    # ------------------------------------------------------------------
    def px(self, logical: float) -> int:
        """論理ピクセル -> 現在のディスプレイの物理ピクセル（ディスプレイの DPI × ユーザーの拡大率）。"""
        return int(round(logical * self.scale * self.zoom))

    @property
    def width_px(self) -> int:
        """ウィンドウの現在の物理幅。配置には必ずこれを使い、metrics.bar_width は使わない。"""
        return self.px(self.bar_width)

    def _clamp_zoom(self, value) -> float:
        try:
            value = round(float(value), 2)
        except (TypeError, ValueError):
            return 1.0
        return min(_ZOOM_MAX, max(_ZOOM_MIN, value))

    def _clamp_width(self, logical) -> int:
        """論理幅を [最小幅, ディスプレイの作業領域の幅] の範囲に収める。"""
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
        """フォントを作る。すでにあればサイズだけ変える——拡大縮小のたびに何度も呼ばれる。

        負のフォントサイズ = ピクセル指定。tk 独自の DPI 換算の影響を受けない。
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
            pass                                   # 読み取り専用のフォルダーでもそのまま使える

    # ------------------------------------------------------------------
    # 画面の構築
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """画面全体を一から組み立てる。拡大縮小のたびに丸ごとやり直すので、再入可能でなければならない。"""
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
            self.bar, self.multiline, self._on_change, self._on_scroll,
            font=self.font_input,
            bg=p.bg, fg=p.fg, insertbackground=p.fg, bd=0, relief="flat",
            highlightthickness=0, exportselection=False,
            selectbackground=p.select_bg, selectforeground=p.select_fg,
            insertwidth=max(1, self.px(2)),
        )
        self.entry = self.box.widget          # 配置やイベントの割り当てで使う

        flat = dict(bd=0, padx=0, pady=0, highlightthickness=0, anchor="w")
        self.placeholder = tk.Label(
            self.bar, bg=p.bg, fg=p.placeholder, font=self.font_placeholder,
            text=("1 行に 1 ステップ。行頭に show と書くと途中結果を表示" if self.multiline
                  else "式を入力（例： 2**3  や  tanh(2)）"),
            **flat)
        self.result = tk.Label(self.bar, text="", bg=p.bg, fg=p.muted,
                               font=self.font_result, **flat)
        # 複数行モードでは表示行ごとに結果ラベルを 1 つ用意する。足りればよく、余りは隠す。
        # 1 つ余分に用意する：ホイールはピクセル単位でスクロールするので上下に半行ずつ見えることがあり、その半行にも結果が要る。
        self._line_labels = [
            tk.Label(self.bar, text="", bg=p.bg, fg=p.muted,
                     font=self.font_result, **flat)
            for _ in range(_MAX_VISIBLE_LINES + 1)] if self.multiline else []

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
        """ボタンは常に右端に置く——ウィンドウの幅が変わったら置き直す。"""
        m = self.metrics
        size = self.px(m.button_size)
        self.button.place(x=self.width_px - self.px(m.button_margin) - size,
                          y=(self.px(m.bar_height) - size) // 2,
                          width=size, height=size)

    # -- 記号パネル --------------------------------------------------------
    def _build_panel(self) -> None:
        """ウィジェットを作るだけ。どこに置くかは _layout_panel が現在の幅に合わせて決める。"""
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
        """現在のウィンドウ幅に合わせてパネルを並べ直す：入りきらない chip は折り返し、ついでに panel_height を求める。"""
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
        """どのボタンにもマウスが乗っていないときに下部に出すショートカットの行——モードによって違う。"""
        return HINT_MULTI if self.multiline else HINT

    def _set_hint(self, text: str) -> None:
        """パネル下部の 1 行。ウィンドウを狭くしたら切り詰めて、ウィンドウの外にはみ出さないようにする。"""
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
    # イベントの割り当て
    # ------------------------------------------------------------------
    def _bind_widgets(self) -> None:
        """ウィジェットに付けるイベント。拡大縮小でウィジェットを作り直すので、これも付け直す。"""
        self.entry.bind("<Escape>", lambda _: (self.escape(), "break")[1])
        self.entry.bind("<Control-a>", self._select_all)
        self.entry.bind("<Control-c>", self._copy)
        # Text のクラスバインディングでは Ctrl+K が「行末まで削除」なので、ウィジェットの層で止める
        self.entry.bind("<Control-k>", lambda _: (self.toggle_panel(), "break")[1])
        self.entry.bind("<Control-m>", lambda _: self.toggle_multiline())
        if self.multiline:
            # Enter の改行は Text 自身に任せ、コピーは Ctrl+Enter に譲る。
            # ↑↓ はカーソル移動に残し、履歴は Ctrl+↑↓ に移す
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
        # bar と panel は全幅に広がっているので、左右の端の帯はリサイズ用に譲る
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
        """root に付けるショートカットと右クリックメニュー。プロセス全体で一度だけ付ける。"""
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
        self._menu.add_command(label="結果をコピー　Enter", command=self.commit)
        self._menu.add_command(label="クリア", command=lambda: self.set_text(""))
        self._menu.add_command(label="記号パネル　Ctrl+K", command=self.toggle_panel)
        self._menu.add_command(label="既定のサイズに戻す　Ctrl+0", command=self.reset_size)
        self._menu.add_separator()
        self._menu.add_checkbutton(label="複数行モード　Ctrl+M", variable=self.multiline_var,
                                   command=self.toggle_multiline)
        self._menu.add_checkbutton(label="常に手前に表示", variable=self.topmost,
                                   command=self._apply_topmost)
        self._menu.add_command(label="カスタム変数をクリア", command=self._reset_vars)
        self._menu.add_separator()
        self._menu.add_command(label="終了　Esc", command=self.quit)

    def _popup_menu(self, event) -> None:
        self._menu.entryconfigure(0, label="結果をコピー　Ctrl+Enter" if self.multiline
                                  else "結果をコピー　Enter")
        self._menu.entryconfigure(2, label="パネルを閉じる　Ctrl+K" if self.panel_open
                                  else "記号パネル　Ctrl+K")
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
        self._flash("カスタム変数をクリアしました")

    # -- ドラッグで移動 -----------------------------------------------------------
    def _start_drag(self, event) -> None:
        self._drag_origin = (event.x_root - self.win_x, event.y_root - self.win_y)

    def _on_drag(self, event) -> None:
        if self._drag_origin is None:
            return
        self.win_x = event.x_root - self._drag_origin[0]
        self.win_y = event.y_root - self._drag_origin[1]
        self._apply_geometry()

    # -- 幅のリサイズ --------------------------------------------------------
    def _edge_at(self, x_root: int) -> int:
        """マウスがウィンドウの左 / 右の端にあれば -1 / +1、中ほどなら 0 を返す。"""
        offset = x_root - self.win_x
        edge = max(3, self.px(self.metrics.resize_edge))
        if offset < edge:
            return -1
        if offset > self.width_px - edge:
            return 1
        return 0

    def _hover_edge(self, event) -> None:
        """端ではカーソルを ↔ にする。「ここを引っ張れる」という唯一の手がかり。"""
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
        if side < 0:                      # 左端をドラッグするときは右端を固定する
            self.win_x = win_x0 + int(round((width0 - self.bar_width) * unit))
        self._resize_layout()

    def _release(self, _event) -> None:
        self._resize_origin = None
        self._drag_origin = None

    def _resize_layout(self) -> None:
        """幅が変わった：ボタンとパネルを置き直せば済み、ウィジェットは 1 つも作り直さない。"""
        self._place_button()
        self._layout_panel()
        self._relayout()
        self._apply_geometry()

    # -- 全体の拡大縮小 --------------------------------------------------------
    def zoom_by(self, steps: int) -> str:
        target = self._clamp_zoom(self.zoom + _ZOOM_STEP * steps)
        if target != self.zoom:
            self._apply_zoom(target)
        return "break"

    def reset_size(self) -> str:
        """幅と倍率をどちらも初期値に戻す——設定は保存されるので、逃げ道を用意しておく。"""
        self.bar_width = self._clamp_width(self.metrics.bar_width)
        if self.zoom != 1.0:
            self._apply_zoom(1.0)
        else:
            self._resize_layout()
        self._flash("既定のサイズに戻しました")
        return "break"

    def _apply_zoom(self, zoom: float) -> None:
        """倍率が変わるとフォントサイズとアイコンのピクセルサイズをすべて計算し直す必要があり、画面全体を一度作り直すしかない。"""
        text, caret = self.box.text(), self.box.caret()
        self.zoom = zoom
        self.bar_width = self._clamp_width(self.bar_width)
        self._init_fonts()
        self._rebuild(text, caret)

        area_x, _, area_w, _ = winapi.cursor_work_area()
        self.win_x = max(area_x, min(self.win_x, area_x + area_w - self.width_px))
        self._apply_geometry()

    # ------------------------------------------------------------------
    # ウィンドウの位置と大きさ
    # ------------------------------------------------------------------
    def _place_window(self) -> None:
        width = self.width_px
        area_x, area_y, area_w, area_h = winapi.cursor_work_area()

        self.win_x = self.config.get("x")
        self.win_y = self.config.get("y")
        if not isinstance(self.win_x, int) or not isinstance(self.win_y, int):
            self.win_x = area_x + (area_w - width) // 2
            self.win_y = area_y + int(area_h * 0.22)
        # 前回のディスプレイはもう外されているかもしれないので、見える範囲に引き戻す
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
    # 入力 -> 計算 -> レイアウト
    # ------------------------------------------------------------------
    def insert(self, text: str, caret_back: int = 0) -> None:
        self.box.insert(text, caret_back)

    def set_text(self, text: str) -> None:
        self.box.set_text(text)
        self.box.caret_to_end()

    def text(self) -> str:
        return self.box.text()

    def _sanitize(self, text: str) -> str:
        """制御文字は捨てる。1 行モードでは改行も空白にし、複数行モードでは残す。"""
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
        """1 回の評価 -> (表示する文字, 色)。1 行と複数行でこの判定を共有する。

        ``bare`` は複数行用：代入の行は値だけを表示する。変数名は同じ行の左側に書いてあるので、
        「= v = 282.7」と書くのはただの重複になる。
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
            self.box.set_text(text, notify=False)   # 自分に戻ってこないように

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
        """1 行なら高さは固定。複数行なら行数に合わせて伸び、_MAX_VISIBLE_LINES で頭打ちになったらスクロールに切り替える。"""
        base = self.px(self.metrics.bar_height)
        if not self.multiline:
            return base
        line_h = self.font_input.metrics("linespace")
        pad = max(0, (base - line_h) // 2)
        box = getattr(self, "box", None)
        rows = box.line_count() if box is not None else 1
        return min(rows, _MAX_VISIBLE_LINES) * line_h + pad * 2

    def _right_edge(self) -> int:
        """式の領域で使える右端（その右は電卓ボタン）。"""
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
        """複数行：入力領域が左側を占め、結果は右側に 1 列に並べて行ごとにそろえる。"""
        m = self.metrics
        text_x, gap = self.px(m.text_x), self.px(m.result_gap)
        right = self._right_edge()
        span = max(self.px(80), right - text_x)
        line_h = self.font_input.metrics("linespace")
        pad_y = max(0, (self.px(m.bar_height) - line_h) // 2)

        # 結果列の位置：いちばん長い行が収まる位置にし、30%〜60% の範囲に収めて、入力中にあちこち動かないようにする
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

        # 保存しておく：スクロール時はテキストが変わらないので、これを使って貼り直すだけで済む
        self._result_rows = wanted
        self._result_col = col
        self._result_room = max(self.px(40), right - text_x - col)
        self._result_pad_y = pad_y

        self.root.update_idletasks()          # dlineinfo はレイアウトが確定してからでないと正確でない
        self._place_result_labels()

    def _place_result_labels(self) -> None:
        """結果をそれぞれの行のベースラインに貼る。スクロールで行の位置が変わっても、貼り直せばそろう。"""
        text_x = self.px(self.metrics.text_x)
        ascent = self.font_result.metrics("ascent")
        used = 0
        for index, shown, color in self._result_rows:
            if used >= len(self._line_labels):
                break
            where = self.box.line_metrics(index)
            if where is None:
                continue                       # この行は表示範囲の外にスクロールした
            top, baseline = where
            label = self._line_labels[used]
            used += 1
            label.configure(text=self._fit(shown, self.font_result, self._result_room),
                            fg=color)
            label.place(x=text_x + self._result_col,
                        y=self._result_pad_y + top + baseline - ascent)
        for label in self._line_labels[used:]:
            label.place_forget()

    def _on_scroll(self) -> None:
        """入力欄の表示範囲が動いた：結果列も貼り直さないと、前の画面の位置に取り残される。

        これは Tk が画面を描いている途中で呼ばれるので、その場でレイアウトを変えるのは安全でない。idle に回す。
        1 回のスクロールで何度も続けて呼ばれるので、フラグで 1 回にまとめる。
        """
        if not self.multiline or self._scroll_pending:
            return
        self._scroll_pending = True
        self.root.after_idle(self._sync_result_labels)

    def _sync_result_labels(self) -> None:
        try:
            if self.multiline and self.box is not None:   # 作り直しの合間にはないことがある
                self._place_result_labels()
        finally:
            # 貼り終えてから解除する：ラベルを貼ること自体は表示範囲を動かさないので、その間の呼び出しはこだまにすぎず、捨ててよい
            self._scroll_pending = False

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
            room = int((right - text_x) * 0.55)       # 式には少なくとも 45% の幅を残す
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
        """結果が長すぎるときは途中を省略し、右のボタンにぶつからないようにする。"""
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
    # 操作
    # ------------------------------------------------------------------
    def commit(self) -> str:
        if self.multiline:
            self._commit_script()
            return "break"
        result = self.current
        if result is None:
            return "break"
        if not result.ok or not result.display:
            self._flash(result.error or "式がまだ書きかけです", error=True)
            return "break"
        self.evaluator.commit(result)
        winapi.set_clipboard_text(format_value(result.value))
        expression = self.box.text().strip()
        if expression and (not self.history or self.history[-1] != expression):
            self.history.append(expression)
            del self.history[:-_HISTORY_LIMIT]
        self.history_index = len(self.history)
        self._select_all()
        self._flash("クリップボードにコピーしました")
        return "break"

    def _commit_script(self) -> None:
        """複数行：表示されている最後の行の値をコピーし、下書きのブロック全体を複数行の履歴に入れる。"""
        last = next((line for line in reversed(self.script)
                     if line.shown and line.result.ok and line.result.display), None)
        if last is None:
            self._flash("コピーできる結果がまだありません", error=True)
            return
        self.evaluator.commit(last.result)
        winapi.set_clipboard_text(format_value(last.result.value))
        block = self.box.text().strip()
        if block and (not self.history_multi or self.history_multi[-1] != block):
            self.history_multi.append(block)
            del self.history_multi[:-_MULTI_HISTORY_LIMIT]
        self.history_index = len(self.history_multi)
        self._flash("クリップボードにコピーしました")

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

    # -- 1 行 / 複数行 ------------------------------------------------------
    def toggle_multiline(self) -> str:
        """2 つのモードはそれぞれ別の下書きを持つ：切り替えた先は空で、戻ると残っている。"""
        self._drafts[self.multiline] = self.box.text()
        self.multiline = not self.multiline
        self.multiline_var.set(self.multiline)
        self._rebuild(self._drafts[self.multiline])
        history = self.history_multi if self.multiline else self.history
        self.history_index = len(history)
        self._flash("複数行モード：1 行に 1 ステップ、行頭に show で途中結果を表示" if self.multiline
                    else "1 行モード")
        return "break"

    def _rebuild(self, text: str, caret: str | None = None) -> None:
        """ウィジェットの種類やフォントサイズが変わったら、画面全体を一度組み直すしかない。

        テキストは呼び出し側がすでに取り出しているので、ここでは先に box を外してから壊す：そうしないと _build の途中で
        _bar_height が破棄済みのウィジェットに問い合わせ、複数行モードではそのまま TclError になる。
        外した後は 1 行として計算され、最後の _on_change が本当の高さに戻す。
        """
        self.box = None
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

    # -- 短いお知らせ（「コピーしました」など。1 秒後に自動で結果表示に戻る） -----------------------
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
