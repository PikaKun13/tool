using System;
using System.Collections.Generic;

namespace KKCalendar.Core
{
    /// <summary>
    /// 按《国民の祝日に関する法律》及其历次修订，纯规则地算出某一年的祝日・休日。
    /// 1948-07-20 施行之前没有祝日；春分/秋分取自天文表（1900–2100）。
    /// 内閣府的官方 CSV 只覆盖到明年，再往后就靠这里。
    /// </summary>
    public static class HolidayRules
    {
        public const string Substitute = "振替休日";
        public const string Citizens = "国民の休日";

        static readonly DateTime LawStart = new DateTime(1948, 7, 20);
        static readonly DateTime SubstituteStart = new DateTime(1973, 4, 12);
        static readonly DateTime CitizensStart = new DateTime(1985, 12, 27);
        static readonly DateTime Revision2007 = new DateTime(2007, 1, 1);

        public static bool Supports(int year) =>
            year >= LawStart.Year && year <= AstroTables.LastYear;

        public static SortedDictionary<DateTime, string> ForYear(int year)
        {
            var result = new SortedDictionary<DateTime, string>();
            if (!Supports(year))
                return result;

            foreach (var pair in NationalHolidays(year))
                if (pair.Key >= LawStart)
                    result[pair.Key] = pair.Value;

            var shukujitsu = new HashSet<DateTime>(result.Keys);
            var substitutes = new List<DateTime>();

            // 振替休日
            foreach (var day in shukujitsu)
            {
                if (day.DayOfWeek != DayOfWeek.Sunday || day < SubstituteStart)
                    continue;
                var next = day.AddDays(1);
                if (day < Revision2007)
                {
                    // 旧法：只看「翌日」，翌日本身就是祝日的话就没有振替
                    if (!shukujitsu.Contains(next))
                        substitutes.Add(next);
                }
                else
                {
                    // 2007 年起：往后找最近的一个「不是祝日」的日子
                    while (shukujitsu.Contains(next))
                        next = next.AddDays(1);
                    substitutes.Add(next);
                }
            }
            foreach (var day in substitutes)
                if (day.Year == year)
                    result[day] = Substitute;

            // 国民の休日：前一天和后一天都是祝日的日子
            foreach (var day in shukujitsu)
            {
                var middle = day.AddDays(1);
                if (middle < CitizensStart || middle.Year != year)
                    continue;
                if (shukujitsu.Contains(middle) || !shukujitsu.Contains(middle.AddDays(1)))
                    continue;
                if (middle < Revision2007)
                {
                    // 旧法：日曜日和振替休日不算
                    if (middle.DayOfWeek == DayOfWeek.Sunday || result.ContainsKey(middle))
                        continue;
                }
                if (!result.ContainsKey(middle))
                    result[middle] = Citizens;
            }
            return result;
        }

        /// <summary>法律直接写明的「国民の祝日」，以及按特别法当作祝日的那几天。</summary>
        static IEnumerable<KeyValuePair<DateTime, string>> NationalHolidays(int y)
        {
            KeyValuePair<DateTime, string> On(int month, int day, string name) =>
                new KeyValuePair<DateTime, string>(new DateTime(y, month, day), name);

            if (y >= 1949)
                yield return On(1, 1, "元日");

            if (y >= 2000)
                yield return On(1, NthMonday(y, 1, 2), "成人の日");
            else if (y >= 1949)
                yield return On(1, 15, "成人の日");

            if (y >= 1967)
                yield return On(2, 11, "建国記念の日");

            if (y >= 2020)
                yield return On(2, 23, "天皇誕生日");

            if (y >= 1949)
                yield return On(3, AstroTables.VernalEquinoxDay[y - AstroTables.FirstYear], "春分の日");

            if (y >= 2007)
                yield return On(4, 29, "昭和の日");
            else if (y >= 1989)
                yield return On(4, 29, "みどりの日");
            else if (y >= 1949)
                yield return On(4, 29, "天皇誕生日");

            if (y >= 1949)
                yield return On(5, 3, "憲法記念日");
            if (y >= 2007)
                yield return On(5, 4, "みどりの日");
            if (y >= 1949)
                yield return On(5, 5, "こどもの日");

            // 海の日（2020、2021 年因东京奥运挪过）
            if (y == 2020)
                yield return On(7, 23, "海の日");
            else if (y == 2021)
                yield return On(7, 22, "海の日");
            else if (y >= 2003)
                yield return On(7, NthMonday(y, 7, 3), "海の日");
            else if (y >= 1996)
                yield return On(7, 20, "海の日");

            // 山の日（同上）
            if (y == 2020)
                yield return On(8, 10, "山の日");
            else if (y == 2021)
                yield return On(8, 8, "山の日");
            else if (y >= 2016)
                yield return On(8, 11, "山の日");

            if (y >= 2003)
                yield return On(9, NthMonday(y, 9, 3), "敬老の日");
            else if (y >= 1966)
                yield return On(9, 15, "敬老の日");

            yield return On(9, AstroTables.AutumnalEquinoxDay[y - AstroTables.FirstYear], "秋分の日");

            // 体育の日 → スポーツの日（2020 年改名；2020、2021 年因奥运挪到 7 月）
            if (y == 2020)
                yield return On(7, 24, "スポーツの日");
            else if (y == 2021)
                yield return On(7, 23, "スポーツの日");
            else if (y >= 2022)
                yield return On(10, NthMonday(y, 10, 2), "スポーツの日");
            else if (y >= 2000)
                yield return On(10, NthMonday(y, 10, 2), "体育の日");
            else if (y >= 1966)
                yield return On(10, 10, "体育の日");

            yield return On(11, 3, "文化の日");
            yield return On(11, 23, "勤労感謝の日");

            if (y >= 1989 && y <= 2018)
                yield return On(12, 23, "天皇誕生日");

            // 特别法规定的一次性休日（按祝日对待）
            switch (y)
            {
                case 1959: yield return On(4, 10, "結婚の儀"); break;
                case 1989: yield return On(2, 24, "大喪の礼"); break;
                case 1990: yield return On(11, 12, "即位礼正殿の儀"); break;
                case 1993: yield return On(6, 9, "結婚の儀"); break;
                case 2019:
                    yield return On(5, 1, "天皇の即位の日");
                    yield return On(10, 22, "即位礼正殿の儀");
                    break;
            }
        }

        /// <summary>某月第 n 个星期一是几号（Happy Monday 制度）。</summary>
        public static int NthMonday(int year, int month, int n)
        {
            var first = new DateTime(year, month, 1);
            int offset = ((int)DayOfWeek.Monday - (int)first.DayOfWeek + 7) % 7;
            return 1 + offset + 7 * (n - 1);
        }
    }
}
