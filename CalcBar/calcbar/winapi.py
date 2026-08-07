"""Windows 平台相关的小工具：DPI、圆角、剪贴板、深浅色、显示器工作区。

全部用 ctypes 调系统 API，不需要 pywin32；任何一项失败都只是降级，不影响计算。
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
    """开启 per-monitor v2 DPI 感知，否则高分屏上字是糊的。"""
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
    """鼠标所在显示器的缩放倍数（125% -> 1.25）。

    不用窗口句柄取，是因为 tk 设了 overrideredirect 之后会重建窗口，
    早期拿到的 HWND 会失效。
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
# 窗口外观
# --------------------------------------------------------------------------

_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_DWMWCP_ROUNDSMALL = 3


def toplevel_hwnd(widget) -> int:
    """拿到 tk 窗口真正的顶层 HWND。"""
    ident = widget.winfo_id()
    parent = user32.GetParent(wintypes.HWND(ident))
    return int(parent) if parent else int(ident)


def round_corners(hwnd: int, small: bool = False) -> bool:
    """让 Win11 的 DWM 给无边框窗口画抗锯齿圆角 + 阴影。"""
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
    """无边框窗口不会自动拿到焦点，手动抢一下。"""
    try:
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
    except OSError:
        pass


# --------------------------------------------------------------------------
# 显示器
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
    """鼠标所在显示器的工作区 (x, y, w, h)，任务栏已排除。"""
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
# 剪贴板
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
    """写系统剪贴板。用 Win32 是为了程序退出后内容还在。"""
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
# 系统主题
# --------------------------------------------------------------------------

def prefers_dark() -> bool:
    """跟随 Windows 的“应用模式”。"""
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
