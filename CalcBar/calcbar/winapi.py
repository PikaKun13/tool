"""Windows 固有の小道具：DPI、角丸、クリップボード、ライト / ダーク、ディスプレイの作業領域。

すべて ctypes でシステム API を呼ぶので pywin32 は不要。どれが失敗しても機能が控えめになるだけで、計算には影響しない。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:                                   # pragma: no cover
    dwmapi = None


# --------------------------------------------------------------------------
# DPI
# --------------------------------------------------------------------------

def enable_dpi_awareness() -> None:
    """per-monitor v2 の DPI 対応を有効にする。しないと高 DPI 画面で文字がぼやける。"""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _system_dpi_scale() -> float:
    try:
        hdc = user32.GetDC(0)
        dpi = ctypes.WinDLL("gdi32").GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        user32.ReleaseDC(0, hdc)
        if dpi:
            return dpi / 96.0
    except OSError:
        pass
    return 1.0


def cursor_dpi_scale() -> float:
    """マウスのあるディスプレイの拡大率（125% -> 1.25）。

    ウィンドウハンドルから取らないのは、tk が overrideredirect を設定するとウィンドウを作り直し、
    早い段階で取った HWND が無効になるため。
    """
    try:
        point = _POINT()
        user32.GetCursorPos(ctypes.byref(point))
        monitor = user32.MonitorFromPoint(point, 2)            # NEAREST
        x = wintypes.UINT()
        y = wintypes.UINT()
        shcore = ctypes.WinDLL("shcore")
        if shcore.GetDpiForMonitor(wintypes.HMONITOR(monitor), 0,
                                   ctypes.byref(x), ctypes.byref(y)) == 0 and x.value:
            return x.value / 96.0
    except (AttributeError, OSError):
        pass
    return _system_dpi_scale()


# --------------------------------------------------------------------------
# ウィンドウの外観
# --------------------------------------------------------------------------

_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_DWMWCP_ROUNDSMALL = 3


def toplevel_hwnd(widget) -> int:
    """tk ウィンドウの本当のトップレベル HWND を取得する。"""
    ident = widget.winfo_id()
    parent = user32.GetParent(wintypes.HWND(ident))
    return int(parent) if parent else int(ident)


def round_corners(hwnd: int, small: bool = False) -> bool:
    """Win11 の DWM に、枠なしウィンドウのアンチエイリアス付き角丸 + 影を描かせる。"""
    if dwmapi is None:
        return False
    value = ctypes.c_int(_DWMWCP_ROUNDSMALL if small else _DWMWCP_ROUND)
    try:
        hr = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(_DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(value), ctypes.sizeof(value))
        return hr == 0
    except OSError:
        return False


def focus_window(hwnd: int) -> None:
    """枠なしウィンドウは自動でフォーカスを得ないので、手動で取りにいく。"""
    try:
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
    except OSError:
        pass


# --------------------------------------------------------------------------
# ディスプレイ
# --------------------------------------------------------------------------

class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


def cursor_work_area() -> tuple[int, int, int, int]:
    """マウスのあるディスプレイの作業領域 (x, y, w, h)。タスクバーは除く。"""
    try:
        point = _POINT()
        user32.GetCursorPos(ctypes.byref(point))
        monitor = user32.MonitorFromPoint(point, 2)            # NEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(wintypes.HMONITOR(monitor), ctypes.byref(info)):
            rect = info.rcWork
            return (rect.left, rect.top,
                    rect.right - rect.left, rect.bottom - rect.top)
    except OSError:
        pass
    return (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


# --------------------------------------------------------------------------
# クリップボード
# --------------------------------------------------------------------------

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]


def set_clipboard_text(text: str) -> bool:
    """システムのクリップボードに書き込む。Win32 を使うのは、プログラム終了後も内容が残るようにするため。"""
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        payload = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(payload))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()


# --------------------------------------------------------------------------
# システムのテーマ
# --------------------------------------------------------------------------

def prefers_dark() -> bool:
    """Windows の「アプリモード」に追従する。"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        with key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except OSError:
        return False
