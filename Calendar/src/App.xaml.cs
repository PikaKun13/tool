using System;
using System.Linq;
using System.Threading;
using System.Windows;
using System.Windows.Threading;
using KKCalendar.Core;
using Microsoft.Win32;

namespace KKCalendar
{
    /// <summary>
    /// 常驻托盘。只允许一个实例：再启动一次 exe 就是把已经在跑的那个的日历弹出来。
    /// </summary>
    public partial class App : Application
    {
        const string MutexName = @"Local\KKCalendar.SingleInstance";
        const string ShowEventName = @"Local\KKCalendar.Show";
        const string ExitEventName = @"Local\KKCalendar.Exit";
        public const string ExitArg = "--exit";

        Mutex? _mutex;
        EventWaitHandle? _showEvent, _exitEvent;
        RegisteredWaitHandle? _showWait, _exitWait;
        Settings _settings = new Settings();
        HolidayBook _book = null!;
        HolidaySource _source;
        TrayIcon? _tray;
        PopupWindow? _popup;
        DispatcherTimer? _clock;
        DateTime _today = DateTime.Today;

        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);
            DispatcherUnhandledException += (s, args) =>
            {
                Settings.Log("未处理的异常: " + args.Exception);
                args.Handled = true;
            };
            AppDomain.CurrentDomain.UnhandledException += (s, args) =>
                Settings.Log("致命异常: " + args.ExceptionObject);

            if (DevTools.TryRun(e.Args, this))
                return;

            bool exitOnly = e.Args.Contains(ExitArg);
            _mutex = new Mutex(true, MutexName, out bool first);
            if (!first || exitOnly)
            {
                // 已经有一个在跑：让它弹出日历（或者退出），自己退出
                Native.AllowSetForegroundWindow(Native.ASFW_ANY);
                try { EventWaitHandle.OpenExisting(exitOnly ? ExitEventName : ShowEventName).Set(); }
                catch (Exception) { }
                Shutdown();
                return;
            }
            _showEvent = new EventWaitHandle(false, EventResetMode.AutoReset, ShowEventName);
            _showWait = ThreadPool.RegisterWaitForSingleObject(_showEvent,
                (state, timedOut) => Dispatcher.BeginInvoke(new Action(ShowFromCorner)), null, -1, false);
            _exitEvent = new EventWaitHandle(false, EventResetMode.AutoReset, ExitEventName);
            _exitWait = ThreadPool.RegisterWaitForSingleObject(_exitEvent,
                (state, timedOut) => Dispatcher.BeginInvoke(new Action(ExitApp)), null, -1, true);

            StartTray();
            if (!e.Args.Contains(AutoStart.BackgroundArg))
                ShowFromCorner();     // 手动双击启动时弹一下，让人知道它在了
        }

        internal void StartTray()
        {
            _settings = Settings.Load();
            _book = HolidayBook.Load(Settings.HolidayCsvPath, out _source);
            _popup = new PopupWindow(_book, _settings.ShowRokuyo);

            _tray = new TrayIcon { RokuyoChecked = _settings.ShowRokuyo };
            _tray.LeftClick += TogglePopup;
            _tray.OpenRequested += ShowFromCorner;
            _tray.UpdateRequested += UpdateHolidays;
            _tray.RokuyoToggled += show =>
            {
                _settings.ShowRokuyo = show;
                _settings.Save();
                _popup.SetShowRokuyo(show);
                RefreshTray();
            };
            _tray.ExitRequested += ExitApp;
            RefreshDataInfo();
            RefreshTray();
            _tray.Show();

            // 过了零点 / 从睡眠醒来 / 改了系统时间：都靠这个轮询发现，开销可以忽略
            _clock = new DispatcherTimer { Interval = TimeSpan.FromSeconds(15) };
            _clock.Tick += (s, e) => CheckDate();
            _clock.Start();
            SystemEvents.TimeChanged += OnTimeChanged;
            SystemEvents.UserPreferenceChanged += OnPreferenceChanged;
            SystemEvents.DisplaySettingsChanged += OnDisplayChanged;
        }

        void OnTimeChanged(object? sender, EventArgs e) => Dispatcher.BeginInvoke(new Action(CheckDate));

        void OnDisplayChanged(object? sender, EventArgs e) => Dispatcher.BeginInvoke(new Action(RefreshTray));

        void OnPreferenceChanged(object? sender, UserPreferenceChangedEventArgs e)
        {
            // 深浅色、强调色的切换都走 General
            if (e.Category != UserPreferenceCategory.General && e.Category != UserPreferenceCategory.Color)
                return;
            Dispatcher.BeginInvoke(new Action(() =>
            {
                _popup?.ApplyTheme(Theme.Current());
                RefreshTray();
            }));
        }

        void CheckDate()
        {
            if (DateTime.Today == _today)
                return;
            _today = DateTime.Today;
            _popup?.TodayChanged();
            RefreshTray();
        }

        void RefreshTray()
        {
            if (_tray == null)
                return;
            var today = DateTime.Today;
            string? holiday = _book.NameOf(today);
            string tip = $"KKCalendar\n{today.Month}月{today.Day}日（{"日月火水木金土"[(int)today.DayOfWeek]}）";
            if (holiday != null)
                tip += " " + holiday;
            else if (_settings.ShowRokuyo && Kyureki.Rokuyo(today) is string rokuyo)
                tip += " " + rokuyo;
            if (_book.NextAfter(today) is { } next)
                tip += $"\n次の祝日 {next.Key.Month}/{next.Key.Day} {next.Value}";
            _tray.Refresh(today, holiday != null, tip);
        }

        void RefreshDataInfo()
        {
            string when = _source.Downloaded ? $"{_source.UpdatedAt:yyyy/MM/dd} 更新" : "程序内置";
            _tray?.SetDataInfo($"祝日数据收录到 {_book.OfficialLastYear} 年（{when}）");
        }

        // ------------------------------------------------------------------
        // 弹出 / 收起
        // ------------------------------------------------------------------

        void TogglePopup()
        {
            if (_popup == null)
                return;
            if (_popup.IsVisible)
            {
                _popup.HidePopup();
                return;
            }
            // 日历开着时点托盘图标：按下那一刻日历已经因失焦收起了，这次点击就别再把它弹出来
            if (unchecked(Environment.TickCount - _popup.LastHiddenAt) < 400)
                return;
            _popup.ShowNear(Native.CursorPosition());
        }

        /// <summary>不是从托盘点出来的（比如双击 exe）：弹在主显示器右下角。</summary>
        void ShowFromCorner()
        {
            var corner = new Native.POINT
            {
                X = Native.GetSystemMetrics(0) - 1,      // SM_CXSCREEN
                Y = Native.GetSystemMetrics(1) - 1,      // SM_CYSCREEN
            };
            _popup?.ShowNear(corner);
        }

        // ------------------------------------------------------------------
        // 更新日历
        // ------------------------------------------------------------------

        async void UpdateHolidays()
        {
            if (_tray == null)
                return;
            _tray.UpdateEnabled = false;
            try
            {
                int lastYear = await HolidayUpdater.DownloadAsync();
                _book = HolidayBook.Load(Settings.HolidayCsvPath, out _source);
                _popup?.SetBook(_book);
                _tray.Notify("KKCalendar", $"祝日数据已更新（内閣府），收录到 {lastYear} 年。");
            }
            catch (Exception ex)
            {
                Settings.Log("更新失败: " + ex);
                _tray.Notify("KKCalendar", "更新失败：" + Describe(ex) + "\n继续使用现有数据。", error: true);
            }
            finally
            {
                _tray.UpdateEnabled = true;
                RefreshDataInfo();
                RefreshTray();
            }
        }

        static string Describe(Exception ex)
        {
            var inner = ex;
            while (inner.InnerException != null)
                inner = inner.InnerException;
            if (ex is System.Net.Http.HttpRequestException || ex is System.Net.WebException)
                return "连不上内閣府的网站（" + inner.Message + "）";
            if (ex is System.Threading.Tasks.TaskCanceledException)
                return "连接超时";
            if (ex is FormatException)
                return "下载到的不是祝日 CSV";
            return inner.Message;
        }

        // ------------------------------------------------------------------
        // 退出
        // ------------------------------------------------------------------

        void ExitApp()
        {
            _tray?.Dispose();
            _tray = null;
            Shutdown();
        }

        protected override void OnExit(ExitEventArgs e)
        {
            SystemEvents.TimeChanged -= OnTimeChanged;
            SystemEvents.UserPreferenceChanged -= OnPreferenceChanged;
            SystemEvents.DisplaySettingsChanged -= OnDisplayChanged;
            _tray?.Dispose();                // 不收掉的话托盘里会留个「幽灵」图标，鼠标划过才消失
            _showWait?.Unregister(null);
            _exitWait?.Unregister(null);
            _showEvent?.Dispose();
            _exitEvent?.Dispose();
            _mutex?.Dispose();
            base.OnExit(e);
        }

        internal PopupWindow? Popup => _popup;
    }
}
