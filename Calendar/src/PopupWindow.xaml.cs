using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using KKCalendar.Core;

namespace KKCalendar
{
    /// <summary>トレイから開くカレンダー。一度だけ作り、あとは Show / Hide を繰り返す。</summary>
    public partial class PopupWindow : Window
    {
        static readonly string[] Weekdays = { "日", "月", "火", "水", "木", "金", "土" };
        static readonly DateTime FirstMonth = new DateTime(AstroTables.FirstYear, 1, 1);
        static readonly DateTime LastMonth = new DateTime(AstroTables.LastYear, 12, 1);
        const double CellSize = 46;

        readonly DayCell[] _cells = new DayCell[42];
        HolidayBook _book;
        bool _showRokuyo;
        Theme _theme = Theme.Current();
        DateTime _today = DateTime.Today;
        DateTime _month = new DateTime(DateTime.Today.Year, DateTime.Today.Month, 1);
        IntPtr _hwnd;
        bool _acrylic;
        Native.POINT _anchor;
        int _wheel;

        /// <summary>開発用のスクリーンショット向け：フォーカスを失っても閉じない。</summary>
        internal bool StayOpen { get; set; }

        /// <summary>最後に閉じた時刻（Environment.TickCount）。</summary>
        internal int LastHiddenAt { get; private set; } = int.MinValue / 2;

        internal PopupWindow(HolidayBook book, bool showRokuyo)
        {
            _book = book;
            _showRokuyo = showRokuyo;
            InitializeComponent();
            BuildGrid();
            ApplyTheme(_theme);

            PrevButton.Click += (s, e) => Step(-1);
            NextButton.Click += (s, e) => Step(1);
            TodayButton.Click += (s, e) => GoTo(_today, 0);
            SourceInitialized += OnSourceInitialized;
            Deactivated += (s, e) => { if (!StayOpen) HidePopup(); };
            DpiChanged += (s, e) => Dispatcher.BeginInvoke(new Action(Place),
                                                            System.Windows.Threading.DispatcherPriority.Loaded);
        }

        // ------------------------------------------------------------------
        // 公開メソッド
        // ------------------------------------------------------------------

        /// <summary>anchor のあるディスプレイのタスクバーの横に開き、今月を表示する。</summary>
        internal void ShowNear(Native.POINT anchor, DateTime? month = null)
        {
            _anchor = anchor;
            _today = DateTime.Today;
            var target = month ?? _today;
            _month = new DateTime(target.Year, target.Month, 1);
            Render();

            new WindowInteropHelper(this).EnsureHandle();
            Place();
            if (!IsVisible)
                Show();
            Place();                 // 表示後に実際のサイズでもう一度配置する（DPI の違うディスプレイでは変わる）
            Activate();
            Native.ForceForeground(_hwnd);
            Focus();
            PlayOpenAnimation();
        }

        internal void HidePopup()
        {
            if (!IsVisible)
                return;
            Hide();
            LastHiddenAt = Environment.TickCount;
        }

        internal void SetBook(HolidayBook book)
        {
            _book = book;
            if (IsVisible) Render();
        }

        internal void SetShowRokuyo(bool show)
        {
            _showRokuyo = show;
            if (IsVisible) Render();
        }

        /// <summary>日付が変わった（0 時を過ぎた、スリープから復帰した）。</summary>
        internal void TodayChanged()
        {
            _today = DateTime.Today;
            if (IsVisible) Render();
        }

        internal void ApplyTheme(Theme theme)
        {
            _theme = theme;
            Resources["TextBrush"] = Theme.Brush(theme.Text);
            Resources["SecondaryBrush"] = Theme.Brush(theme.Secondary);
            Resources["TertiaryBrush"] = Theme.Brush(theme.Tertiary);
            Resources["SeparatorBrush"] = Theme.Brush(theme.Separator);
            Resources["HoverBrush"] = Theme.Brush(theme.Hover);
            Resources["PressedBrush"] = Theme.Brush(theme.Pressed);
            ApplyBackdrop();
            RenderWeekHeader();
            Render();
        }

        // ------------------------------------------------------------------
        // ウィンドウの外観と位置
        // ------------------------------------------------------------------

        void OnSourceInitialized(object? sender, EventArgs e)
        {
            _hwnd = new WindowInteropHelper(this).Handle;
            var source = HwndSource.FromHwnd(_hwnd);
            if (source?.CompositionTarget != null)
                source.CompositionTarget.BackgroundColor = Colors.Transparent;
            Native.RoundCorners(_hwnd);
            Native.DisableDwmTransitions(_hwnd);   // システムの拡大アニメーションを、自前のスライドアップに置き換える
            _acrylic = Native.TryAcrylic(_hwnd);
            ApplyBackdrop();
        }

        void ApplyBackdrop()
        {
            if (_hwnd != IntPtr.Zero)
                Native.SetDarkFrame(_hwnd, _theme.Dark);
            // アクリルが使えるなら半透明の下地を 1 枚重ねる（壁紙がにぎやかでも文字が読めるように）。使えない（Win10 / 古い Win11）なら単色
            var bg = _theme.Background;
            Root.Background = Theme.Brush(_acrylic ? Color.FromArgb(0xB0, bg.R, bg.G, bg.B) : bg);
        }

        /// <summary>タスクバーに沿って右下に置く（タスクバーがほかの辺にあればその辺に沿わせる）。</summary>
        void Place()
        {
            if (_hwnd == IntPtr.Zero)
                return;
            var area = Native.MonitorAt(_anchor);
            int w, h;
            if (IsVisible && Native.GetWindowRect(_hwnd, out var rect))
            {
                w = rect.Width;
                h = rect.Height;
            }
            else
            {
                Root.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
                w = (int)Math.Ceiling(Root.DesiredSize.Width * area.Scale);
                h = (int)Math.Ceiling(Root.DesiredSize.Height * area.Scale);
            }

            int margin = (int)Math.Round(12 * area.Scale);
            var mon = area.Monitor;
            var work = area.Work;
            int x = work.Right - w - margin;
            int y = work.Bottom - h - margin;
            if (work.Top > mon.Top)                      // タスクバーが上
                y = work.Top + margin;
            else if (work.Left > mon.Left)               // タスクバーが左
                x = work.Left + margin;
            else if (work.Bottom == mon.Bottom && work.Right == mon.Right
                     && _anchor.Y < (mon.Top + mon.Bottom) / 2)
                y = work.Top + margin;                   // 自動的に隠れるタスクバーが上
            x = Math.Max(work.Left, Math.Min(x, work.Right - w));
            y = Math.Max(work.Top, Math.Min(y, work.Bottom - h));
            Native.MoveWindow(_hwnd, x, y);
        }

        void PlayOpenAnimation()
        {
            var ease = new CubicEase { EasingMode = EasingMode.EaseOut };
            var duration = TimeSpan.FromMilliseconds(220);
            BodySlide.BeginAnimation(TranslateTransform.YProperty,
                new DoubleAnimation(18, 0, duration) { EasingFunction = ease });
            Body.BeginAnimation(OpacityProperty, new DoubleAnimation(0, 1, duration) { EasingFunction = ease });
        }

        // ------------------------------------------------------------------
        // 月の移動
        // ------------------------------------------------------------------

        void Step(int months) => GoTo(_month.AddMonths(months), Math.Sign(months));

        void GoTo(DateTime date, int direction)
        {
            var month = new DateTime(date.Year, date.Month, 1);
            if (month < FirstMonth) month = FirstMonth;
            if (month > LastMonth) month = LastMonth;
            if (direction == 0)
                direction = Math.Sign((month - _month).Days);
            if (month == _month)
                return;
            _month = month;
            Render();

            var duration = TimeSpan.FromMilliseconds(160);
            var ease = new CubicEase { EasingMode = EasingMode.EaseOut };
            DaysSlide.BeginAnimation(TranslateTransform.YProperty,
                new DoubleAnimation(10 * direction, 0, duration) { EasingFunction = ease });
            Days.BeginAnimation(OpacityProperty, new DoubleAnimation(0.25, 1, duration) { EasingFunction = ease });
        }

        protected override void OnMouseWheel(MouseWheelEventArgs e)
        {
            // タッチパッドは一度に数十の delta しか来ないので、120 たまったら 1 か月めくる
            _wheel += e.Delta;
            while (_wheel >= 120) { Step(-1); _wheel -= 120; }
            while (_wheel <= -120) { Step(1); _wheel += 120; }
            e.Handled = true;
        }

        protected override void OnPreviewKeyDown(KeyEventArgs e)
        {
            switch (e.Key)
            {
                case Key.Escape: HidePopup(); break;
                case Key.Left: case Key.Up: case Key.PageUp: Step(-1); break;
                case Key.Right: case Key.Down: case Key.PageDown: Step(1); break;
                case Key.Home: GoTo(_today, 0); break;
                default: return;
            }
            e.Handled = true;
        }

        // ------------------------------------------------------------------
        // 描画
        // ------------------------------------------------------------------

        void BuildGrid()
        {
            for (int i = 0; i < Weekdays.Length; i++)
                WeekHeader.Children.Add(new TextBlock
                {
                    Text = Weekdays[i],
                    FontSize = 12,
                    HorizontalAlignment = HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Center,
                });
            for (int i = 0; i < _cells.Length; i++)
            {
                var cell = new DayCell(this);
                _cells[i] = cell;
                Days.Children.Add(cell.Box);
            }
        }

        void RenderWeekHeader()
        {
            for (int i = 0; i < Weekdays.Length; i++)
            {
                var block = (TextBlock)WeekHeader.Children[i];
                block.Foreground = Theme.Brush(i == 0 ? _theme.Sunday : i == 6 ? _theme.Saturday : _theme.Tertiary);
            }
        }

        void Render()
        {
            RenderToday();
            MonthTitle.Text = $"{_month.Year}年{_month.Month}月";
            MonthEra.Text = Wareki.Format(_month) ?? "";

            var first = _month.AddDays(-(int)_month.DayOfWeek);   // 日曜始まり
            for (int i = 0; i < _cells.Length; i++)
                _cells[i].Update(first.AddDays(i));
            RenderHolidayList();
        }

        void RenderToday()
        {
            TodayTitle.Text = $"{_today.Month}月{_today.Day}日 {Weekdays[(int)_today.DayOfWeek]}曜日";

            TodaySub.Inlines.Clear();
            TodaySub.Inlines.Add(new Run($"{_today.Year}年・{Wareki.Format(_today)}"));
            var rokuyo = _showRokuyo ? Kyureki.Rokuyo(_today) : null;
            if (rokuyo != null)
                TodaySub.Inlines.Add(new Run("・" + rokuyo));
            var holiday = _book.NameOf(_today);
            if (holiday != null)
            {
                TodaySub.Inlines.Add(new Run("・"));
                TodaySub.Inlines.Add(new Run(holiday) { Foreground = Theme.Brush(_theme.Sunday) });
            }

            var next = _book.NextAfter(_today);
            if (next is KeyValuePair<DateTime, string> pair)
            {
                int days = (pair.Key - _today).Days;
                NextHoliday.Text = $"次の祝日　{pair.Key.Month}月{pair.Key.Day}日（{Weekdays[(int)pair.Key.DayOfWeek]}）" +
                                   $"{pair.Value}・あと{days}日";
                NextHoliday.Visibility = Visibility.Visible;
            }
            else
            {
                NextHoliday.Visibility = Visibility.Collapsed;
            }
        }

        void RenderHolidayList()
        {
            HolidayList.Children.Clear();
            HolidayList.RowDefinitions.Clear();
            HolidayList.ColumnDefinitions.Clear();

            var items = _book.InMonth(_month.Year, _month.Month);
            if (items.Count == 0)
            {
                HolidayList.Children.Add(new TextBlock
                {
                    Text = "この月は祝日がありません",
                    FontSize = 12.5,
                    Foreground = Theme.Brush(_theme.Tertiary),
                });
                return;
            }

            // 1 列は最大 4 行。超えたら（2019 年 5 月など）2 列に分け、日付を短く書く
            int columns = items.Count > 4 ? 2 : 1;
            int rows = (items.Count + columns - 1) / columns;
            for (int c = 0; c < columns; c++)
                HolidayList.ColumnDefinitions.Add(new ColumnDefinition());
            for (int r = 0; r < rows; r++)
                HolidayList.RowDefinitions.Add(new RowDefinition { Height = new GridLength(20) });

            for (int i = 0; i < items.Count; i++)
            {
                var date = items[i].Key;
                var line = new StackPanel { Orientation = Orientation.Horizontal };
                line.Children.Add(new TextBlock
                {
                    Text = columns == 1 ? $"{date.Day}日（{Weekdays[(int)date.DayOfWeek]}）" : $"{date.Day}日",
                    Width = columns == 1 ? 68 : 32,
                    FontSize = 12.5,
                    Foreground = Theme.Brush(_theme.Sunday),
                });
                line.Children.Add(new TextBlock
                {
                    Text = items[i].Value,
                    FontSize = 12.5,
                    Foreground = Theme.Brush(_theme.Text),
                    TextTrimming = TextTrimming.CharacterEllipsis,
                });
                Grid.SetColumn(line, i / rows);
                Grid.SetRow(line, i % rows);
                HolidayList.Children.Add(line);
            }
        }

        /// <summary>カレンダーの 1 マス：日付の数字 + 六曜。</summary>
        sealed class DayCell
        {
            readonly PopupWindow _owner;
            readonly TextBlock _number, _sub;
            Brush _restBackground = Brushes.Transparent;
            bool _highlighted;
            public readonly Border Box;
            public DateTime Date;

            public DayCell(PopupWindow owner)
            {
                _owner = owner;
                _number = new TextBlock { FontSize = 15, HorizontalAlignment = HorizontalAlignment.Center };
                _sub = new TextBlock { FontSize = 9.5, HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 1, 0, 0) };
                var stack = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
                stack.Children.Add(_number);
                stack.Children.Add(_sub);
                Box = new Border
                {
                    Height = CellSize - 4,
                    Margin = new Thickness(2),
                    CornerRadius = new CornerRadius(6),
                    Background = Brushes.Transparent,
                    Child = stack,
                };
                ToolTipService.SetInitialShowDelay(Box, 350);
                Box.MouseEnter += (s, e) => { if (!_highlighted) Box.Background = Theme.Brush(_owner._theme.Hover); };
                Box.MouseLeave += (s, e) => Box.Background = _restBackground;
                Box.MouseLeftButtonUp += (s, e) =>
                {
                    if (Date.Month != _owner._month.Month)
                        _owner.GoTo(Date, Date < _owner._month ? -1 : 1);
                };
            }

            public void Update(DateTime date)
            {
                Date = date;
                var theme = _owner._theme;
                bool inMonth = date.Month == _owner._month.Month;
                bool today = date == _owner._today;
                string? holiday = _owner._book.NameOf(date);
                string? rokuyo = _owner._showRokuyo ? Kyureki.Rokuyo(date) : null;

                Color ink = holiday != null || date.DayOfWeek == DayOfWeek.Sunday ? theme.Sunday
                          : date.DayOfWeek == DayOfWeek.Saturday ? theme.Saturday
                          : theme.Text;
                Color subInk = holiday != null ? theme.Sunday : theme.Tertiary;
                _highlighted = today;
                if (today)
                {
                    ink = subInk = theme.OnAccent;
                    _restBackground = Theme.Brush(theme.Accent);
                }
                else
                {
                    _restBackground = Brushes.Transparent;
                }

                _number.Text = date.Day.ToString();
                _number.Foreground = Theme.Brush(ink);
                _number.FontWeight = today || holiday != null ? FontWeights.SemiBold : FontWeights.Normal;
                _sub.Text = rokuyo ?? "";
                _sub.Foreground = Theme.Brush(subInk);
                _sub.Visibility = rokuyo == null ? Visibility.Collapsed : Visibility.Visible;
                Box.Background = _restBackground;
                Box.Opacity = inMonth ? 1.0 : 0.38;
                Box.Cursor = inMonth ? null : Cursors.Hand;

                string tip = $"{date.Year}年{date.Month}月{date.Day}日（{Weekdays[(int)date.DayOfWeek]}）";
                if (holiday != null) tip += "\n" + holiday;
                if (rokuyo != null) tip += "\n" + rokuyo;
                Box.ToolTip = tip;
            }
        }
    }
}
