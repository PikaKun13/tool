using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.Windows;
using System.Windows.Threading;
using KKCalendar.Core;

namespace KKCalendar
{
    /// <summary>
    /// 開発用のコマンドラインオプション（ふだんの利用には影響しない）：
    ///   KKCalendar.exe --screenshot out.png [2026-09] [dark|light]   カレンダーを表示してスクリーンショットを撮り、終了
    ///   KKCalendar.exe --tray-preview out.png                        各サイズのトレイアイコンを 1 枚の画像に描く
    /// </summary>
    internal static class DevTools
    {
        public static bool TryRun(string[] args, App app)
        {
            if (args.Length >= 2 && args[0] == "--screenshot")
            {
                Screenshot(args, app);
                return true;
            }
            if (args.Length >= 2 && args[0] == "--tray-preview")
            {
                TrayPreview(args[1]);
                app.Shutdown();
                return true;
            }
            if (args.Length >= 2 && args[0] == "--update-check")
            {
                UpdateCheck(args[1], app);
                return true;
            }
            return false;
        }

        /// <summary>「祝日データを更新」を実際に 1 回実行し、結果をテキストファイルに書き出す。</summary>
        static async void UpdateCheck(string output, App app)
        {
            string result;
            try
            {
                int lastYear = await HolidayUpdater.DownloadAsync();
                var book = HolidayBook.Load(Settings.HolidayCsvPath, out var source);
                result = $"ok lastYear={lastYear} downloaded={source.Downloaded} official={book.OfficialFirstYear}-{book.OfficialLastYear}"
                       + $" path={Settings.HolidayCsvPath}";
            }
            catch (Exception ex)
            {
                result = "error " + ex;
            }
            System.IO.File.WriteAllText(output, result);
            app.Shutdown();
        }

        static void Screenshot(string[] args, App app)
        {
            DateTime? month = null;
            for (int i = 2; i < args.Length; i++)
            {
                if (args[i] == "dark") Theme.ForceDark = true;
                else if (args[i] == "light") Theme.ForceDark = false;
                else if (DateTime.TryParseExact(args[i], "yyyy-MM", CultureInfo.InvariantCulture,
                                                DateTimeStyles.None, out var m)) month = m;
            }

            var book = HolidayBook.Load(null, out _);
            var popup = new PopupWindow(book, showRokuyo: true) { StayOpen = true };
            var corner = new Native.POINT { X = Native.GetSystemMetrics(0) - 1, Y = Native.GetSystemMetrics(1) - 1 };
            popup.ShowNear(corner, month);

            var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(900) };
            timer.Tick += (s, e) =>
            {
                timer.Stop();
                var hwnd = new System.Windows.Interop.WindowInteropHelper(popup).Handle;
                Native.GetWindowRect(hwnd, out var r);
                int pad = 16;
                using (var shot = new Bitmap(r.Width + pad * 2, r.Height + pad * 2))
                {
                    using (var g = Graphics.FromImage(shot))
                        g.CopyFromScreen(r.Left - pad, r.Top - pad, 0, 0, shot.Size);
                    shot.Save(args[1], ImageFormat.Png);
                }
                app.Shutdown();
            };
            timer.Start();
        }

        static void TrayPreview(string path)
        {
            int[] sizes = { 16, 20, 24, 32 };
            const int zoom = 4;
            int cellW = 32 * zoom + 16;
            using (var sheet = new Bitmap(cellW * sizes.Length + 8, (32 * zoom + 16) * 4))
            using (var g = Graphics.FromImage(sheet))
            {
                g.InterpolationMode = InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode = PixelOffsetMode.Half;
                int row = 0;
                foreach (bool light in new[] { false, true })
                    foreach (bool holiday in new[] { false, true })
                    {
                        int y = row * (32 * zoom + 16);
                        using (var bg = new SolidBrush(light ? Color.FromArgb(0xEE, 0xEE, 0xEE) : Color.FromArgb(0x1C, 0x1C, 0x1C)))
                            g.FillRectangle(bg, 0, y, sheet.Width, 32 * zoom + 16);
                        for (int i = 0; i < sizes.Length; i++)
                            using (var icon = TrayIconPainter.Render(holiday ? 23 : 13, sizes[i], light, holiday))
                            {
                                int x = 8 + i * cellW;
                                g.DrawImage(icon, new Rectangle(x, y + 8, sizes[i] * zoom, sizes[i] * zoom));
                            }
                        row++;
                    }
                sheet.Save(path, ImageFormat.Png);
            }
        }
    }
}
