using System;

namespace KKCalendar.Core
{
    /// <summary>和暦（元号）。只用来显示，不需要 JapaneseCalendar 那套。</summary>
    public static class Wareki
    {
        // (改元日, 元号, 元年对应的公历年)。日历只显示 1900 年以后，明治的起点粗略即可
        static readonly (DateTime Start, string Name, int FirstYear)[] Eras =
        {
            (new DateTime(2019, 5, 1), "令和", 2019),
            (new DateTime(1989, 1, 8), "平成", 1989),
            (new DateTime(1926, 12, 25), "昭和", 1926),
            (new DateTime(1912, 7, 30), "大正", 1912),
            (new DateTime(1868, 1, 1), "明治", 1868),
        };

        /// <summary>例如 2026-11-13 →「令和8年」，2019-05-01 →「令和元年」。</summary>
        public static string? Format(DateTime date)
        {
            foreach (var era in Eras)
            {
                if (date.Date < era.Start)
                    continue;
                int year = date.Year - era.FirstYear + 1;
                return era.Name + (year == 1 ? "元" : year.ToString()) + "年";
            }
            return null;
        }
    }
}
