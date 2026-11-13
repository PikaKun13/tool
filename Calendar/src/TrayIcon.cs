using System;
using System.Drawing;
using System.Windows.Forms;

namespace KKCalendar
{
    /// <summary>
    /// トレイアイコンと右クリックメニュー。メニューはネイティブの HMENU（WinForms の旧 ContextMenu）なので、
    /// 見た目はシステムのほかのトレイメニューと同じで、ダークモードにも追従する。
    /// </summary>
    internal sealed class TrayIcon : IDisposable
    {
        readonly NotifyIcon _icon = new NotifyIcon();
        readonly MenuItem _open, _update, _dataInfo, _rokuyo, _autoStart, _exit;
        Icon? _current;

        public event Action? LeftClick;
        public event Action? OpenRequested;
        public event Action? UpdateRequested;
        public event Action<bool>? RokuyoToggled;
        public event Action? ExitRequested;

        public TrayIcon()
        {
            _open = new MenuItem("カレンダーを開く", (s, e) => OpenRequested?.Invoke()) { DefaultItem = true };
            _update = new MenuItem("祝日データを更新", (s, e) => UpdateRequested?.Invoke());
            _dataInfo = new MenuItem("") { Enabled = false };
            _rokuyo = new MenuItem("六曜を表示", (s, e) =>
            {
                _rokuyo!.Checked = !_rokuyo.Checked;
                RokuyoToggled?.Invoke(_rokuyo.Checked);
            });
            _autoStart = new MenuItem("スタートアップに登録", (s, e) => ToggleAutoStart());
            _exit = new MenuItem("終了", (s, e) => ExitRequested?.Invoke());

            var menu = new ContextMenu(new[]
            {
                _open,
                new MenuItem("-"),
                _update,
                _dataInfo,
                new MenuItem("-"),
                _rokuyo,
                _autoStart,
                new MenuItem("-"),
                _exit,
            });
            menu.Popup += (s, e) =>
            {
                Native.SetMenuDarkMode(!Theme.TaskbarIsLight());
                _autoStart.Checked = AutoStart.IsEnabled;
            };
            _icon.ContextMenu = menu;
            _icon.MouseClick += (s, e) =>
            {
                if (e.Button == MouseButtons.Left)
                    LeftClick?.Invoke();
            };
        }

        public bool RokuyoChecked
        {
            get => _rokuyo.Checked;
            set => _rokuyo.Checked = value;
        }

        public bool UpdateEnabled
        {
            set
            {
                _update.Enabled = value;
                _update.Text = value ? "祝日データを更新" : "更新中…";
            }
        }

        public void SetDataInfo(string text) => _dataInfo.Text = text;

        public void Show() => _icon.Visible = true;

        /// <summary>アイコンを描き直す（日付、タスクバーのライト / ダーク、DPI が変わったときに呼ぶ）。</summary>
        public void Refresh(DateTime today, bool holiday, string tooltip)
        {
            using (var bitmap = TrayIconPainter.Render(today.Day, Native.SmallIconSize(), Theme.TaskbarIsLight(), holiday))
            {
                var icon = TrayIconPainter.ToIcon(bitmap);
                _icon.Icon = icon;
                _current?.Dispose();
                _current = icon;
            }
            // NotifyIcon.Text は 63 文字を超えると例外を投げる
            _icon.Text = tooltip.Length > 63 ? tooltip.Substring(0, 63) : tooltip;
        }

        public void Notify(string title, string text, bool error = false) =>
            _icon.ShowBalloonTip(5000, title, text, error ? ToolTipIcon.Warning : ToolTipIcon.Info);

        void ToggleAutoStart()
        {
            try
            {
                AutoStart.Set(!AutoStart.IsEnabled);
            }
            catch (Exception ex)
            {
                Notify("KKCalendar", "スタートアップの設定に失敗しました：" + ex.Message, error: true);
            }
        }

        public void Dispose()
        {
            _icon.Visible = false;
            _icon.Dispose();
            _current?.Dispose();
        }
    }
}
