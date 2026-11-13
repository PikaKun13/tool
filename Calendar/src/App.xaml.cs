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
    /// トレイに常駐。インスタンスは 1 つだけ：exe をもう一度起動すると、すでに動いているほうのカレンダーを表示する。
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
                Settings.Log("未処理の例外: " + args.Exception);
                args.Handled = true;
            };
            AppDomain.CurrentDomain.UnhandledException += (s, args) =>
                Settings.Log("致命的な例外: " + args.ExceptionObject);

            if (DevTools.TryRun(e.Args, this))
                return;

            bool exitOnly = e.Args.Contains(ExitArg);
            _mutex = new Mutex(true, MutexName, out bool first);
            if (!first || exitOnly)
            {
                // すでに 1 つ動いている：そちらにカレンダーを表示させ（または終了させ）、自分は終了する
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
                ShowFromCorner();     // 手動で起動したときは一度表示して、起動したことがわかるようにする
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

            // 0 時を過ぎた / スリープから復帰した / システム時刻を変えた：どれもこのポーリングで検知する。負荷は無視できる程度
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
            // ライト / ダークやアクセントカラーの切り替えは、どれも General で届く
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
            string when = _source.Downloaded ? $"{_source.UpdatedAt:yyyy/MM/dd} 更新" : "内蔵データ";
            _tray?.SetDataInfo($"祝日データ：{_book.OfficialLastYear} 年まで（{when}）");
        }

        // ------------------------------------------------------------------
        // 表示 / 非表示
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
            // カレンダーが開いているときにトレイアイコンをクリック：押した瞬間にフォーカスを失って閉じているので、このクリックでまた開かないようにする
            if (unchecked(Environment.TickCount - _popup.LastHiddenAt) < 400)
                return;
            _popup.ShowNear(Native.CursorPosition());
        }

        /// <summary>トレイからではなく（exe のダブルクリックなどで）開くとき：メインディスプレイの右下に表示する。</summary>
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
        // 祝日データの更新
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
                _tray.Notify("KKCalendar", $"祝日データを更新しました（内閣府）。{lastYear} 年まで収録されています。");
            }
            catch (Exception ex)
            {
                Settings.Log("更新失敗: " + ex);
                _tray.Notify("KKCalendar", "更新に失敗しました：" + Describe(ex) + "\n今のデータをそのまま使います。", error: true);
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
                return "内閣府のサイトに接続できません（" + inner.Message + "）";
            if (ex is System.Threading.Tasks.TaskCanceledException)
                return "接続がタイムアウトしました";
            if (ex is FormatException)
                return "ダウンロードしたファイルが祝日 CSV ではありません";
            return inner.Message;
        }

        // ------------------------------------------------------------------
        // 終了
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
            _tray?.Dispose();                // 片付けないとトレイに「幽霊」アイコンが残り、マウスを乗せるまで消えない
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
