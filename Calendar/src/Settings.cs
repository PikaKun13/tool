using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace KKCalendar
{
    /// <summary>
    /// 设置和下载的数据放在 exe 旁边（绿色版）；那里写不了（比如放进了 Program Files）
    /// 就退到 %LOCALAPPDATA%\KKCalendar。不写注册表。
    /// </summary>
    internal sealed class Settings
    {
        public static string DataDirectory { get; } = PickDataDirectory();
        public static string IniPath => Path.Combine(DataDirectory, "KKCalendar.ini");
        public static string HolidayCsvPath => Path.Combine(DataDirectory, "syukujitsu.csv");
        public static string LogPath => Path.Combine(DataDirectory, "KKCalendar.log");

        public bool ShowRokuyo { get; set; } = true;

        public static Settings Load()
        {
            var settings = new Settings();
            try
            {
                if (!File.Exists(IniPath))
                    return settings;
                var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                foreach (var raw in File.ReadAllLines(IniPath, Encoding.UTF8))
                {
                    var line = raw.Trim();
                    int eq = line.IndexOf('=');
                    if (line.StartsWith(";") || eq <= 0)
                        continue;
                    values[line.Substring(0, eq).Trim()] = line.Substring(eq + 1).Trim();
                }
                if (values.TryGetValue("ShowRokuyo", out var rokuyo))
                    settings.ShowRokuyo = rokuyo != "0";
            }
            catch (Exception) { }
            return settings;
        }

        public void Save()
        {
            try
            {
                File.WriteAllText(IniPath,
                    "; KKCalendar の設定\r\n" +
                    "ShowRokuyo=" + (ShowRokuyo ? "1" : "0") + "\r\n",
                    new UTF8Encoding(false));
            }
            catch (Exception) { }
        }

        static string PickDataDirectory()
        {
            string exeDir = AppDomain.CurrentDomain.BaseDirectory;
            if (CanWrite(exeDir))
                return exeDir;
            string local = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "KKCalendar");
            try { Directory.CreateDirectory(local); } catch (Exception) { }
            return local;
        }

        static bool CanWrite(string dir)
        {
            try
            {
                string probe = Path.Combine(dir, ".kkcalendar-write-test");
                File.WriteAllText(probe, "");
                File.Delete(probe);
                return true;
            }
            catch (Exception)
            {
                return false;
            }
        }

        public static void Log(string message)
        {
            try
            {
                File.AppendAllText(LogPath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {message}\r\n", Encoding.UTF8);
            }
            catch (Exception) { }
        }
    }
}
