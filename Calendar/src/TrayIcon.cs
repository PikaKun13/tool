using System;
using System.Drawing;
using System.Windows.Forms;

namespace KKCalendar
{
    /// <summary>
    /// 托盘图标和右键菜单。菜单用的是原生 HMENU（WinForms 旧版 ContextMenu），
    /// 所以外观和系统其它托盘菜单一致，深色模式也跟着走。
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
            _open = new MenuItem("打开日历", (s, e) => OpenRequested?.Invoke()) { DefaultItem = true };
            _update = new MenuItem("更新日历", (s, e) => UpdateRequested?.Invoke());
            _dataInfo = new MenuItem("") { Enabled = false };
            _rokuyo = new MenuItem("显示六曜", (s, e) =>
            {
                _rokuyo!.Checked = !_rokuyo.Checked;
                RokuyoToggled?.Invoke(_rokuyo.Checked);
            });
            _autoStart = new MenuItem("开机自动启动", (s, e) => ToggleAutoStart());
            _exit = new MenuItem("退出", (s, e) => ExitRequested?.Invoke());

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
                _update.Text = value ? "更新日历" : "正在更新…";
            }
        }

        public void SetDataInfo(string text) => _dataInfo.Text = text;

        public void Show() => _icon.Visible = true;

        /// <summary>重画图标（日期变了、任务栏深浅色变了、DPI 变了都要调）。</summary>
        public void Refresh(DateTime today, bool holiday, string tooltip)
        {
            using (var bitmap = TrayIconPainter.Render(today.Day, Native.SmallIconSize(), Theme.TaskbarIsLight(), holiday))
            {
                var icon = TrayIconPainter.ToIcon(bitmap);
                _icon.Icon = icon;
                _current?.Dispose();
                _current = icon;
            }
            // NotifyIcon.Text 超过 63 个字符会抛异常
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
                Notify("KKCalendar", "设置开机启动失败：" + ex.Message, error: true);
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
