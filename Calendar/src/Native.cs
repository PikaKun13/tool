using System;
using System.Runtime.InteropServices;

namespace KKCalendar
{
    /// <summary>使っている Win32 / DWM API。どれが失敗しても機能が控えめになるだけで、カレンダー自体には影響しない。</summary>
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
        // ディスプレイ
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
        /// トレイの小アイコンの一辺：100% なら 16、150% なら 24。メインディスプレイの「現在の」DPI で計算する——
        /// GetSystemMetrics が返すのはサインイン時の DPI なので、拡大率を変えてサインアウトしていないと合わない。
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
        // ウィンドウ
        // ------------------------------------------------------------------

        static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        const uint SWP_NOSIZE = 0x0001, SWP_NOACTIVATE = 0x0010;

        public static void MoveWindow(IntPtr hwnd, int x, int y) =>
            SetWindowPos(hwnd, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE);

        /// <summary>
        /// 前面に出る。トレイのクリック時はシステムがフォアグラウンド権限をくれるので、たいていそのまま成功する。
        /// 失敗したら、フォアグラウンドウィンドウの入力キューを借りてもう一度試す。
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
        // DWM：角丸、ダークのタイトルバー、アクリル背景
        // ------------------------------------------------------------------

        const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
        const int DWMWA_TRANSITIONS_FORCEDISABLED = 3;
        const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
        const int DWMWA_SYSTEMBACKDROP_TYPE = 38;
        const int DWMWCP_ROUND = 2;
        const int DWMSBT_TRANSIENTWINDOW = 3;     // ポップアップ用のアクリル

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

        /// <summary>Win11 22H2 以降で対応。false が返ったら呼び出し側は単色の背景にする。</summary>
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
        // メニューのダークモード（uxtheme の非公開の序数エクスポート。Win10 1903 以降のみ）
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
