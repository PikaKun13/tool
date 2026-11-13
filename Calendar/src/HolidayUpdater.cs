using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading.Tasks;
using KKCalendar.Core;

namespace KKCalendar
{
    /// <summary>「更新日历」：重新下载内閣府的祝日 CSV。</summary>
    internal static class HolidayUpdater
    {
        public static async Task<int> DownloadAsync()
        {
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            byte[] data;
            using (var client = new HttpClient { Timeout = TimeSpan.FromSeconds(20) })
            {
                client.DefaultRequestHeaders.UserAgent.ParseAdd("KKCalendar/1.0");
                data = await client.GetByteArrayAsync(HolidayBook.OfficialUrl).ConfigureAwait(false);
            }

            // 先解析一遍，确认是像样的数据再落盘
            var parsed = HolidayBook.ParseCsv(data);
            string target = Settings.HolidayCsvPath;
            string temp = target + ".download";
            File.WriteAllBytes(temp, data);
            if (File.Exists(target))
                File.Delete(target);
            File.Move(temp, target);

            int lastYear = 0;
            foreach (var day in parsed.Keys)
                lastYear = Math.Max(lastYear, day.Year);
            return lastYear;
        }
    }
}
