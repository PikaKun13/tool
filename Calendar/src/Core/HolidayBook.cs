using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace KKCalendar.Core
{
    /// <summary>
    /// 祝日の照会。内閣府 CSV に含まれる年は CSV を正とし（公式）、それ以外の年は法律の規定どおりに計算する。
    /// </summary>
    public sealed class HolidayBook
    {
        public const string OfficialUrl = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv";

        readonly Dictionary<DateTime, string> _official;
        readonly Dictionary<int, SortedDictionary<DateTime, string>> _byYear =
            new Dictionary<int, SortedDictionary<DateTime, string>>();

        /// <summary>CSV に含まれる年の範囲。CSV がないときはどちらも 0。</summary>
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
                    // CSV では振替休日も国民の休日も「休日」、特別法による日は「休日（祝日扱い）」と書かれているので、
                    // 規則から具体的な名前がわかるものはそちらを使う
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

        /// <summary>今日より後（今日は含まない）の次の祝日。</summary>
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
        /// 内閣府 CSV（Shift_JIS、「yyyy/m/d,名称」）を解析する。形式がおかしければ FormatException を投げて、
        /// 壊れたデータを保存してしまわないようにする。
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
                        throw new FormatException("CSV の行の形式が不正です: " + line);
                    var date = DateTime.ParseExact(line.Substring(0, comma).Trim(), "yyyy/M/d",
                                                   CultureInfo.InvariantCulture);
                    result[date] = line.Substring(comma + 1).Trim();
                }
            }
            if (result.Count < 500)
                throw new FormatException("CSV の祝日が少なすぎます。内閣府のファイルではない可能性があります");
            return result;
        }

        public static byte[] BundledCsv()
        {
            using (var stream = typeof(HolidayBook).Assembly.GetManifestResourceStream("syukujitsu.csv"))
            using (var buffer = new MemoryStream())
            {
                if (stream == null)
                    throw new InvalidOperationException("内蔵の syukujitsu.csv が見つかりません");
                stream.CopyTo(buffer);
                return buffer.ToArray();
            }
        }

        /// <summary>
        /// ダウンロード済みの CSV（収録年がより新しいほう）を優先して読み、読めなければ内蔵のものを使う。
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

        /// <summary>true = ネットからダウンロードした CSV、false = プログラムに内蔵のもの。</summary>
        public bool Downloaded { get; }
        public DateTime UpdatedAt { get; }
    }
}
