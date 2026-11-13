using System;
using System.IO;
using System.Reflection;

namespace KKCalendar
{
    /// <summary>开机自启：在「启动」文件夹里放一个快捷方式（不写注册表，删掉快捷方式就关了）。</summary>
    internal static class AutoStart
    {
        public const string BackgroundArg = "--background";

        static string ShortcutPath => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Startup), "KKCalendar.lnk");

        static string ExePath => Assembly.GetEntryAssembly()!.Location;

        /// <summary>快捷方式存在、而且指向的就是当前这个 exe。</summary>
        public static bool IsEnabled
        {
            get
            {
                if (!File.Exists(ShortcutPath))
                    return false;
                try
                {
                    dynamic shell = CreateShell();
                    dynamic link = shell.CreateShortcut(ShortcutPath);
                    return string.Equals(Path.GetFullPath((string)link.TargetPath), ExePath,
                                         StringComparison.OrdinalIgnoreCase);
                }
                catch (Exception)
                {
                    return false;
                }
            }
        }

        public static void Set(bool enabled)
        {
            if (!enabled)
            {
                if (File.Exists(ShortcutPath))
                    File.Delete(ShortcutPath);
                return;
            }
            dynamic shell = CreateShell();
            dynamic link = shell.CreateShortcut(ShortcutPath);
            link.TargetPath = ExePath;
            link.Arguments = BackgroundArg;
            link.WorkingDirectory = Path.GetDirectoryName(ExePath);
            link.Description = "KKCalendar";
            link.Save();
        }

        static object CreateShell() =>
            Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell", throwOnError: true)!)!;
    }
}
