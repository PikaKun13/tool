"""开发用：把界面拉起来、填好内容、截自己窗口的图，然后退出。

    python tools/shoot.py <输出png> [算式] [panel]
"""

import sys
from ctypes import byref, windll
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import ImageGrab                       # noqa: E402

from calcbar import winapi                     # noqa: E402
from calcbar.ui import CalcBar                  # noqa: E402


def main() -> None:
    out = sys.argv[1]
    expression = sys.argv[2] if len(sys.argv) > 2 else ""
    flags = sys.argv[3:]
    want_panel = "panel" in flags
    if "dark" in flags:
        winapi.prefers_dark = lambda: True

    app = CalcBar()
    app.win_x, app.win_y = 300, 300
    if want_panel != app.panel_open:
        app.toggle_panel()
    app._apply_geometry()
    if expression:
        app.set_text(expression)

    def shoot() -> None:
        rect = wintypes.RECT()
        windll.user32.GetWindowRect(wintypes.HWND(app.hwnd), byref(rect))
        margin = 24
        ImageGrab.grab(bbox=(rect.left - margin, rect.top - margin,
                             rect.right + margin, rect.bottom + margin),
                       all_screens=True).save(out)
        app.root.destroy()

    app.root.after(900, shoot)
    app.root.mainloop()
    print("saved", out)


if __name__ == "__main__":
    main()
