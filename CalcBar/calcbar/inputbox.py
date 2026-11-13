"""1 行の ``Entry`` と複数行の ``Text`` を同じインターフェースで包む。

2 つのウィジェットの API はまるで違う（``get()`` と ``get("1.0","end-1c")``、``icursor`` と
``mark_set``、``textvariable`` の有無…）。``ui.py`` のあちこちに ``if 複数行`` を書いたら、
あのファイルはすぐ読めなくなる。だからテキストの取得・変更、カーソル、選択範囲といった処理はすべてここにまとめ、
``ui.py`` はどこに置くか、結果をどこに描くかだけを扱う。

変更通知はすべて ``_notify`` を通す：今のテキストを前回と比べ、本当に変わったときだけコールバックするので、
「キー入力」「貼り付け」「プログラムによる書き換え」の 3 経路から重ねて呼ばれても余計な計算はしない。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable


class InputBox:
    """式の入力欄。``multiline`` で中身が Entry か Text かが決まる。"""

    def __init__(self, parent: tk.Misc, multiline: bool,
                 on_change: Callable[[], None],
                 on_scroll: Callable[[], None] | None = None, **style) -> None:
        self.multiline = multiline
        self._on_change = on_change
        self._last_seen = ""

        if multiline:
            self.var = None
            self.widget = tk.Text(parent, wrap="none", undo=True,
                                  spacing1=0, spacing2=0, spacing3=0,
                                  padx=0, pady=0, **style)
            self.widget.bind("<KeyRelease>", lambda _: self._notify())
            self.widget.bind("<<Modified>>", self._on_modified)
            if on_scroll is not None:
                # テキストは変わらないのに表示範囲だけ動く経路は多すぎる（ホイール、カーソルに引っ張られる、端までドラッグ選択して
                # 自動スクロール、see()）。1 つずつ割り当てると、1 つ漏れただけでずれる。yscrollcommand は Tk が
                # 表示範囲が変わった後に自分で呼ぶので、ここ 1 か所ですべて拾える。
                self.widget.configure(yscrollcommand=lambda *_: on_scroll())
        else:
            self.var = tk.StringVar(master=parent)
            self.var.trace_add("write", lambda *_: self._notify())
            self.widget = tk.Entry(parent, textvariable=self.var, **style)

    # ------------------------------------------------------------------
    # 変更通知
    # ------------------------------------------------------------------
    def _notify(self) -> None:
        current = self.text()
        if current != self._last_seen:
            self._last_seen = current
            self._on_change()

    def _on_modified(self, _event) -> None:
        """Text の最後の砦となる通知：マウスのドラッグや元に戻すなど、KeyRelease を伴わない変更。"""
        self.widget.edit_modified(False)
        self._notify()

    # ------------------------------------------------------------------
    # テキストの取得 / 変更
    # ------------------------------------------------------------------
    def text(self) -> str:
        if self.multiline:
            return self.widget.get("1.0", "end-1c")
        return self.var.get()

    def set_text(self, value: str, notify: bool = True) -> None:
        """``notify=False`` は「on_change の中で整えたテキストを書き戻す」とき用。呼び出しが自分に戻ってこないようにする。"""
        if not notify:
            self._last_seen = value
        if self.multiline:
            self.widget.delete("1.0", "end")
            self.widget.insert("1.0", value)
            self.widget.edit_modified(False)
        else:
            self.var.set(value)
        if notify:
            self._notify()

    def insert(self, text: str, caret_back: int = 0) -> None:
        """カーソル位置に挿入する。``caret_back`` は挿入後にカーソルを何文字戻すか。"""
        self.focus()
        if self.multiline:
            if self.widget.tag_ranges("sel"):
                self.widget.delete("sel.first", "sel.last")
            self.widget.insert("insert", text)
            if caret_back:
                self.widget.mark_set("insert", f"insert-{caret_back}c")
        else:
            if self.widget.selection_present():
                self.widget.delete("sel.first", "sel.last")
            index = self.widget.index("insert")
            self.widget.insert(index, text)
            self.widget.icursor(index + len(text) - caret_back)
        self._notify()

    # ------------------------------------------------------------------
    # カーソルと選択範囲
    # ------------------------------------------------------------------
    def focus(self) -> None:
        try:
            self.widget.focus_set()
        except tk.TclError:
            pass

    def caret_to_end(self) -> None:
        if self.multiline:
            self.widget.mark_set("insert", "end-1c")
            self.widget.see("insert")
        else:
            self.widget.icursor("end")

    def caret(self) -> str:
        """現在のカーソル位置（形式はウィジェットによる）。作り直した後に元の位置へ戻すためだけに使う。"""
        return str(self.widget.index("insert"))

    def restore_caret(self, where: str) -> None:
        try:
            if self.multiline:
                self.widget.mark_set("insert", where)
            else:
                self.widget.icursor(where)
        except tk.TclError:
            self.caret_to_end()

    def select_all(self) -> None:
        if self.multiline:
            self.widget.tag_add("sel", "1.0", "end-1c")
            self.widget.mark_set("insert", "end-1c")
        else:
            self.widget.select_range(0, "end")
            self.widget.icursor("end")

    def selected_text(self) -> str | None:
        try:
            if self.multiline:
                if not self.widget.tag_ranges("sel"):
                    return None
                return self.widget.get("sel.first", "sel.last")
            if not self.widget.selection_present():
                return None
            return self.widget.selection_get()
        except tk.TclError:
            return None

    # ------------------------------------------------------------------
    # 行単位で見る（複数行モードでだけ使う）
    # ------------------------------------------------------------------
    def lines(self) -> list[str]:
        return self.text().split("\n")

    def line_count(self) -> int:
        return max(1, len(self.lines()))

    def line_metrics(self, index: int) -> tuple[int, int] | None:
        """``index`` 行目（0 始まり）のウィジェット内での ``(上端 y, ベースラインのオフセット)``。

        行が表示範囲の外にスクロールしたら ``None`` を返す——対応する結果ラベルは隠すべき。
        """
        if not self.multiline:
            return None
        try:
            info = self.widget.dlineinfo(f"{index + 1}.0")
        except tk.TclError:
            return None
        return (info[1], info[4]) if info else None

    def destroy(self) -> None:
        self.widget.destroy()
