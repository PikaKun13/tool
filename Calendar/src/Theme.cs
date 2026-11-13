using System;
using System.Windows.Media;
using Microsoft.Win32;

namespace KKCalendar
{
    /// <summary>跟随 Windows 的深浅色和强调色。</summary>
    internal sealed class Theme
    {
        public bool Dark { get; private set; }
        public Color Background, Text, Secondary, Tertiary, Separator, Hover, Pressed;
        public Color Sunday, Saturday, Accent, OnAccent;

        /// <summary>开发截图时强制深色/浅色；null = 跟随系统。</summary>
        internal static bool? ForceDark;

        public static Theme Current()
        {
            bool dark = ForceDark ?? !ReadBool(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", true);
            var t = new Theme { Dark = dark };
            if (dark)
            {
                t.Background = Rgb(0x2B, 0x2B, 0x2B);
                t.Text = Rgb(0xFF, 0xFF, 0xFF);
                t.Secondary = Rgb(0xC8, 0xC8, 0xC8);
                t.Tertiary = Rgb(0x8F, 0x8F, 0x8F);
                t.Separator = Color.FromArgb(0x24, 0xFF, 0xFF, 0xFF);
                t.Hover = Color.FromArgb(0x14, 0xFF, 0xFF, 0xFF);
                t.Pressed = Color.FromArgb(0x0C, 0xFF, 0xFF, 0xFF);
                t.Sunday = Rgb(0xFF, 0x8A, 0x8A);
                t.Saturday = Rgb(0x86, 0xB6, 0xFF);
            }
            else
            {
                t.Background = Rgb(0xF5, 0xF5, 0xF5);
                t.Text = Rgb(0x1A, 0x1A, 0x1A);
                t.Secondary = Rgb(0x5C, 0x5C, 0x5C);
                t.Tertiary = Rgb(0x8C, 0x8C, 0x8C);
                t.Separator = Color.FromArgb(0x1A, 0x00, 0x00, 0x00);
                t.Hover = Color.FromArgb(0x0F, 0x00, 0x00, 0x00);
                t.Pressed = Color.FromArgb(0x08, 0x00, 0x00, 0x00);
                t.Sunday = Rgb(0xC9, 0x2A, 0x2F);
                t.Saturday = Rgb(0x1A, 0x5F, 0xB4);
            }
            // Win11 的「今天」：深色主题用浅一档的强调色配黑字，浅色主题用深一档的配白字
            t.Accent = AccentShade(dark ? 1 : 4) ?? (dark ? Rgb(0x60, 0xCD, 0xFF) : Rgb(0x00, 0x5F, 0xB8));
            t.OnAccent = dark ? Rgb(0x00, 0x00, 0x00) : Rgb(0xFF, 0xFF, 0xFF);
            return t;
        }

        /// <summary>任务栏是浅色还是深色（和「应用」的深浅色是两个独立设置）。</summary>
        public static bool TaskbarIsLight() =>
            ReadBool(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "SystemUsesLightTheme", false);

        public static SolidColorBrush Brush(Color color)
        {
            var brush = new SolidColorBrush(color);
            brush.Freeze();
            return brush;
        }

        static Color Rgb(byte r, byte g, byte b) => Color.FromRgb(r, g, b);

        static bool ReadBool(string path, string name, bool fallback)
        {
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(path))
                    if (key?.GetValue(name) is int value)
                        return value != 0;
            }
            catch (Exception) { }
            return fallback;
        }

        /// <summary>
        /// AccentPalette 是 8 个 RGBA：浅3 浅2 浅1 本色 深1 深2 深3 (未用)。
        /// </summary>
        static Color? AccentShade(int index)
        {
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"))
                    if (key?.GetValue("AccentPalette") is byte[] palette && palette.Length >= 32)
                        return Rgb(palette[index * 4], palette[index * 4 + 1], palette[index * 4 + 2]);
            }
            catch (Exception) { }
            return null;
        }
    }
}
