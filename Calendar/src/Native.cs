using System;
using System.Runtime.InteropServices;

namespace KKCalendar
{
    /// <summary>用到的 Win32 / DWM 接口。任何一项失败都只是降级，不影响日历本身。</summary>
    internal static class Native
    {
        [StructLayout(LayoutKind.Sequential)]
        public struct POINT { public int X, Y; }

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT
        {
            public int Left, Top, Right, Bottom;
            public int Width => Right - Left;
            public int Height => Bottom - Top;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct MONITORINFO
        {
            public int cbSize;
            public RECT rcMonitor;
            public RECT rcWork;
            public uint dwFlags;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct MARGINS { public int Left, Right, Top, Bottom; }

        [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT point);
        [DllImport("user32.dll")] static extern IntPtr MonitorFromPoint(POINT pt, uint flags);
        [DllImport("user32.dll")] static extern bool GetMonitorInfo(IntPtr monitor, ref MONITORINFO info);
        [DllImport("shcore.dll")] static extern int GetDpiForMonitor(IntPtr monitor, int type, out uint dpiX, out uint dpiY);
        [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
        [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr hwnd);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, IntPtr pid);
        [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
        [DllImport("user32.dll")] static extern bool AttachThreadInput(uint from, uint to, bool attach);
        [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int processId);
        [DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr icon);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
        [DllImport("dwmapi.dll")] static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref MARGINS margins);

        public const int ASFW_ANY = -1;
        const int SM_CXSMICON = 49;

        // ------------------------------------------------------------------
        // 显示器
        // ------------------------------------------------------------------

        public sealed class MonitorArea
        {
            public RECT Monitor;
            public RECT Work;
            public double Scale = 1.0;      // 125% -> 1.25
        }

        public static MonitorArea MonitorAt(POINT point)
        {
            var area = new MonitorArea();
            IntPtr monitor = MonitorFromPoint(point, 2);   // MONITOR_DEFAULTTONEAREST
            var info = new MONITORINFO { cbSize = Marshal.SizeOf(typeof(MONITORINFO)) };
            if (GetMonitorInfo(monitor, ref info))
            {
                area.Monitor = info.rcMonitor;
                area.Work = info.rcWork;
            }
            else
            {
                area.Monitor = area.Work = new RECT { Right = GetSystemMetrics(0), Bottom = GetSystemMetrics(1) };
            }
            try
            {
                if (GetDpiForMonitor(monitor, 0, out uint dpi, out _) == 0 && dpi > 0)
                    area.Scale = dpi / 96.0;
            }
            catch (DllNotFoundException) { }
            catch (EntryPointNotFoundException) { }
            return area;
        }

        public static POINT CursorPosition()
        {
            GetCursorPos(out var point);
            return point;
        }

        [DllImport("user32.dll")] static extern int GetSystemMetricsForDpi(int index, uint dpi);

        /// <summary>
        /// 托盘小图标的边长：100% 是 16，150% 是 24。按主显示器「现在」的 DPI 算——
        /// GetSystemMetrics 给的是登录时的 DPI，改了缩放不注销的话就不准了。
        /// </summary>
        public static int SmallIconSize()
        {
            try
            {
                var primary = MonitorFromPoint(new POINT(), 1);          // MONITOR_DEFAULTTOPRIMARY
                if (GetDpiForMonitor(primary, 0, out uint dpi, out _) == 0 && dpi > 0)
                    return Math.Max(16, GetSystemMetricsForDpi(SM_CXSMICON, dpi));
            }
            catch (DllNotFoundException) { }
            catch (EntryPointNotFoundException) { }
            return Math.Max(16, GetSystemMetrics(SM_CXSMICON));
        }

        // ------------------------------------------------------------------
        // 窗口
        // ------------------------------------------------------------------

        static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        const uint SWP_NOSIZE = 0x0001, SWP_NOACTIVATE = 0x0010;

        public static void MoveWindow(IntPtr hwnd, int x, int y) =>
            SetWindowPos(hwnd, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE);

        /// <summary>
        /// 抢前台。托盘点击时系统会给我们前台权限，一般直接成功；
        /// 不成功就借前台窗口的输入队列再试一次。
        /// </summary>
        public static void ForceForeground(IntPtr hwnd)
        {
            if (SetForegroundWindow(hwnd) && GetForegroundWindow() == hwnd)
                return;
            IntPtr foreground = GetForegroundWindow();
            uint target = GetWindowThreadProcessId(foreground, IntPtr.Zero);
            uint self = GetCurrentThreadId();
            if (target != 0 && target != self && AttachThreadInput(self, target, true))
            {
                BringWindowToTop(hwnd);
                SetForegroundWindow(hwnd);
                AttachThreadInput(self, target, false);
            }
        }

        // ------------------------------------------------------------------
        // DWM：圆角、深色标题、亚克力背景
        // ------------------------------------------------------------------

        const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
        const int DWMWA_TRANSITIONS_FORCEDISABLED = 3;
        const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
        const int DWMWA_SYSTEMBACKDROP_TYPE = 38;
        const int DWMWCP_ROUND = 2;
        const int DWMSBT_TRANSIENTWINDOW = 3;     // 弹出层用的亚克力

        static bool SetAttribute(IntPtr hwnd, int attribute, int value)
        {
            try
            {
                return DwmSetWindowAttribute(hwnd, attribute, ref value, sizeof(int)) == 0;
            }
            catch (DllNotFoundException) { return false; }
            catch (EntryPointNotFoundException) { return false; }
        }

        public static void RoundCorners(IntPtr hwnd) => SetAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND);

        public static void DisableDwmTransitions(IntPtr hwnd) => SetAttribute(hwnd, DWMWA_TRANSITIONS_FORCEDISABLED, 1);

        public static void SetDarkFrame(IntPtr hwnd, bool dark) => SetAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, dark ? 1 : 0);

        /// <summary>Win11 22H2 起支持；返回 false 时调用方改用纯色背景。</summary>
        public static bool TryAcrylic(IntPtr hwnd)
        {
            if (Environment.OSVersion.Version.Build < 22621)
                return false;
            var margins = new MARGINS { Left = -1, Right = -1, Top = -1, Bottom = -1 };
            try
            {
                if (DwmExtendFrameIntoClientArea(hwnd, ref margins) != 0)
                    return false;
            }
            catch (DllNotFoundException) { return false; }
            return SetAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW);
        }

        // ------------------------------------------------------------------
        // 菜单深色模式（uxtheme 未公开的序号函数，Win10 1903+ 才有）
        // ------------------------------------------------------------------

        [DllImport("uxtheme.dll", EntryPoint = "#135")] static extern int SetPreferredAppMode(int mode);
        [DllImport("uxtheme.dll", EntryPoint = "#136")] static extern void FlushMenuThemes();

        public static void SetMenuDarkMode(bool dark)
        {
            try
            {
                SetPreferredAppMode(dark ? 2 : 3);    // ForceDark / ForceLight
                FlushMenuThemes();
            }
            catch (EntryPointNotFoundException) { }
            catch (DllNotFoundException) { }
        }
    }
}
