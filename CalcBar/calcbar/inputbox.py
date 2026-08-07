"""把单行 ``Entry`` 和多行 ``Text`` 包成同一套接口。

两种控件的 API 完全不通（``get()`` 对 ``get("1.0","end-1c")``、``icursor`` 对
``mark_set``、有没有 ``textvariable``…）。如果让 ``ui.py`` 到处 ``if 多行``，
那个文件很快就没法看了。所以取文本、改文本、光标、选区这些事情都收在这里，
``ui.py`` 只管往哪儿摆、结果画在哪儿。

变更通知统一走 ``_notify``：拿当前文本跟上次比，真变了才回调，
所以「敲键盘」「粘贴」「程序改写」三条路重复触发也不会多算。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable


class InputBox:
    """算式输入区。``multiline`` 决定底下是 Entry 还是 Text。"""

    def __init__(self, parent: tk.Misc, multiline: bool,
                 on_change: Callable[[], None], **style) -> None:
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
        else:
            self.var = tk.StringVar(master=parent)
            self.var.trace_add("write", lambda *_: self._notify())
            self.widget = tk.Entry(parent, textvariable=self.var, **style)

    # ------------------------------------------------------------------
    # 变更通知
    # ------------------------------------------------------------------
    def _notify(self) -> None:
        current = self.text()
        if current != self._last_seen:
            self._last_seen = current
            self._on_change()

    def _on_modified(self, _event) -> None:
        """Text 的兜底信号：鼠标拖拽、撤销这些没有 KeyRelease 的改动。"""
        self.widget.edit_modified(False)
        self._notify()

    # ------------------------------------------------------------------
    # 取 / 改文本
    # ------------------------------------------------------------------
    def text(self) -> str:
        if self.multiline:
            return self.widget.get("1.0", "end-1c")
        return self.var.get()

    def set_text(self, value: str, notify: bool = True) -> None:
        """``notify=False`` 用于「在 on_change 里回写清理过的文本」，避免绕回来。"""
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
        """在光标处插入；``caret_back`` 是插完之后光标往回退几格。"""
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
    # 光标与选区
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
        """当前光标位置，格式随控件；只用来在重建之后放回原处。"""
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
    # 按行看（只有多行模式用得上）
    # ------------------------------------------------------------------
    def lines(self) -> list[str]:
        return self.text().split("\n")

    def line_count(self) -> int:
        return max(1, len(self.lines()))

    def line_metrics(self, index: int) -> tuple[int, int] | None:
        """第 ``index`` 行（0 起）在控件里的 ``(顶边 y, 基线偏移)``。

        行滚出视野时返回 ``None``——对应的结果标签就该藏起来。
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
