using System;
using System.Windows.Media;
using Microsoft.Win32;

namespace KKCalendar
{
    /// <summary>Windows のライト / ダークとアクセントカラーに追従する。</summary>
    internal sealed class Theme
    {
        public bool Dark { get; private set; }
        public Color Background, Text, Secondary, Tertiary, Separator, Hover, Pressed;
        public Color Sunday, Saturday, Accent, OnAccent;

        /// <summary>開発用のスクリーンショットでダーク / ライトを強制する。null = システムに追従。</summary>
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
            // Win11 の「今日」：ダークテーマでは 1 段明るいアクセントカラーに黒文字、ライトテーマでは 1 段暗いものに白文字
            t.Accent = AccentShade(dark ? 1 : 4) ?? (dark ? Rgb(0x60, 0xCD, 0xFF) : Rgb(0x00, 0x5F, 0xB8));
            t.OnAccent = dark ? Rgb(0x00, 0x00, 0x00) : Rgb(0xFF, 0xFF, 0xFF);
            return t;
        }

        /// <summary>タスクバーがライトかダークか（「アプリ」のライト / ダークとは別の設定）。</summary>
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
        /// AccentPalette は 8 個の RGBA：明3 明2 明1 基本色 暗1 暗2 暗3（未使用）。
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
