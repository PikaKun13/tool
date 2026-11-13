using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace KKCalendar.Core
{
    /// <summary>
    /// 祝日查询。内閣府 CSV 覆盖到的年份以 CSV 为准（官方），其余年份按法律规则计算。
    /// </summary>
    public sealed class HolidayBook
    {
        public const string OfficialUrl = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv";

        readonly Dictionary<DateTime, string> _official;
        readonly Dictionary<int, SortedDictionary<DateTime, string>> _byYear =
            new Dictionary<int, SortedDictionary<DateTime, string>>();

        /// <summary>CSV 覆盖的年份范围；没有 CSV 时两者都是 0。</summary>
        public int OfficialFirstYear { get; }
        public int OfficialLastYear { get; }

        public HolidayBook(IDictionary<DateTime, string>? official)
        {
            _official = official == null
                ? new Dictionary<DateTime, string>()
                : new Dictionary<DateTime, string>(official);
            if (_official.Count > 0)
            {
                OfficialFirstYear = _official.Keys.Min().Year;
                OfficialLastYear = _official.Keys.Max().Year;
            }
        }

        public bool IsOfficial(int year) =>
            _official.Count > 0 && year >= OfficialFirstYear && year <= OfficialLastYear;

        public SortedDictionary<DateTime, string> ForYear(int year)
        {
            if (_byYear.TryGetValue(year, out var cached))
                return cached;

            var rules = HolidayRules.ForYear(year);
            SortedDictionary<DateTime, string> result;
            if (IsOfficial(year))
            {
                result = new SortedDictionary<DateTime, string>();
                foreach (var pair in _official)
                {
                    if (pair.Key.Year != year)
                        continue;
                    // CSV 把振替休日、国民の休日都写成「休日」，特别法的日子写成「休日（祝日扱い）」，
                    // 能从规则里查到具体名字的就用具体名字
                    string name = pair.Value;
                    if (IsGenericName(name) && rules.TryGetValue(pair.Key, out var ruleName))
                        name = ruleName;
                    result[pair.Key] = name;
                }
            }
            else
            {
                result = rules;
            }
            _byYear[year] = result;
            return result;
        }

        public static bool IsGenericName(string name) =>
            name == "休日" || name.StartsWith("休日（", StringComparison.Ordinal);

        public string? NameOf(DateTime date)
        {
            ForYear(date.Year).TryGetValue(date.Date, out var name);
            return name;
        }

        public List<KeyValuePair<DateTime, string>> InMonth(int year, int month) =>
            ForYear(year).Where(p => p.Key.Month == month).ToList();

        /// <summary>今天之后（不含今天）的下一个祝日。</summary>
        public KeyValuePair<DateTime, string>? NextAfter(DateTime date)
        {
            for (int year = date.Year; year <= Math.Min(date.Year + 2, AstroTables.LastYear); year++)
                foreach (var pair in ForYear(year))
                    if (pair.Key > date.Date)
                        return pair;
            return null;
        }

        // ------------------------------------------------------------------
        // CSV
        // ------------------------------------------------------------------

        static Encoding ShiftJis => Encoding.GetEncoding(932);

        /// <summary>
        /// 解析内閣府 CSV（Shift_JIS，「yyyy/m/d,名称」）。格式不对就抛 FormatException，
        /// 免得把一份坏数据存下来。
        /// </summary>
        public static Dictionary<DateTime, string> ParseCsv(byte[] data)
        {
            string text = ShiftJis.GetString(data);
            var result = new Dictionary<DateTime, string>();
            using (var reader = new StringReader(text))
            {
                string? line;
                bool header = true;
                while ((line = reader.ReadLine()) != null)
                {
                    if (header) { header = false; continue; }
                    line = line.Trim();
                    if (line.Length == 0)
                        continue;
                    int comma = line.IndexOf(',');
                    if (comma <= 0)
                        throw new FormatException("CSV 行格式不对: " + line);
                    var date = DateTime.ParseExact(line.Substring(0, comma).Trim(), "yyyy/M/d",
                                                   CultureInfo.InvariantCulture);
                    result[date] = line.Substring(comma + 1).Trim();
                }
            }
            if (result.Count < 500)
                throw new FormatException("CSV 里的祝日太少，可能不是内閣府的文件");
            return result;
        }

        public static byte[] BundledCsv()
        {
            using (var stream = typeof(HolidayBook).Assembly.GetManifestResourceStream("syukujitsu.csv"))
            using (var buffer = new MemoryStream())
            {
                if (stream == null)
                    throw new InvalidOperationException("找不到内置的 syukujitsu.csv");
                stream.CopyTo(buffer);
                return buffer.ToArray();
            }
        }

        /// <summary>
        /// 优先读下载过的 CSV（覆盖年份更晚的那份），读不了就用内置的。
        /// </summary>
        public static HolidayBook Load(string? downloadedPath, out HolidaySource source)
        {
            Dictionary<DateTime, string> bundled = ParseCsv(BundledCsv());
            Dictionary<DateTime, string>? downloaded = null;
            DateTime downloadedAt = default;
            if (downloadedPath != null && File.Exists(downloadedPath))
            {
                try
                {
                    downloaded = ParseCsv(File.ReadAllBytes(downloadedPath));
                    downloadedAt = File.GetLastWriteTime(downloadedPath);
                }
                catch (Exception ex) when (ex is IOException || ex is FormatException
                                           || ex is UnauthorizedAccessException)
                {
                    downloaded = null;
                }
            }

            if (downloaded != null && downloaded.Keys.Max() >= bundled.Keys.Max())
            {
                source = new HolidaySource(true, downloadedAt);
                return new HolidayBook(downloaded);
            }
            source = new HolidaySource(false, default);
            return new HolidayBook(bundled);
        }
    }

    public readonly struct HolidaySource
    {
        public HolidaySource(bool downloaded, DateTime updatedAt)
        {
            Downloaded = downloaded;
            UpdatedAt = updatedAt;
        }

        /// <summary>true = 用的是联网下载的 CSV；false = 程序内置的那份。</summary>
        public bool Downloaded { get; }
        public DateTime UpdatedAt { get; }
    }
}
