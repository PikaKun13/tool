using System;
using System.Collections.Generic;
using System.Linq;
using KKCalendar.Core;
using Xunit;

namespace KKCalendar.Tests
{
    public class HolidayTests
    {
        static readonly Dictionary<DateTime, string> Official = HolidayBook.ParseCsv(HolidayBook.BundledCsv());

        static DateTime D(int y, int m, int d) => new DateTime(y, m, d);

        /// <summary>
        /// 规则算出来的，和内閣府 CSV 逐日比对（1955 年至 CSV 的最后一年）。
        /// 两边是独立来源：一边是照法律条文写的规则 + 星历算的春分秋分，一边是官方公布的名单。
        /// </summary>
        [Fact]
        public void RulesMatchCabinetOfficeCsv()
        {
            int first = Official.Keys.Min().Year, last = Official.Keys.Max().Year;
            Assert.Equal(1955, first);
            var problems = new List<string>();
            for (int year = first; year <= last; year++)
            {
                var rules = HolidayRules.ForYear(year);
                var csv = Official.Where(p => p.Key.Year == year).ToDictionary(p => p.Key, p => p.Value);
                foreach (var day in csv.Keys.Except(rules.Keys))
                    problems.Add($"规则漏了 {day:yyyy-MM-dd} {csv[day]}");
                foreach (var day in rules.Keys.Except(csv.Keys))
                    problems.Add($"规则多了 {day:yyyy-MM-dd} {rules[day]}");
                foreach (var day in csv.Keys.Intersect(rules.Keys))
                    if (!NamesAgree(csv[day], rules[day]))
                        problems.Add($"{day:yyyy-MM-dd} 名称不同: CSV={csv[day]} 规则={rules[day]}");
            }
            Assert.True(problems.Count == 0, string.Join("\n", problems));
        }

        static bool NamesAgree(string csv, string rule)
        {
            if (csv == rule)
                return true;
            if (csv == "休日")
                return rule == HolidayRules.Substitute || rule == HolidayRules.Citizens;
            if (csv == "休日（祝日扱い）")
                return rule == "天皇の即位の日" || rule == "即位礼正殿の儀";
            // 2019 年 CSV 写的是「体育の日（スポーツの日）」，法律上那年还叫体育の日
            return csv == "体育の日（スポーツの日）" && rule == "体育の日";
        }

        [Theory]
        [InlineData(2026, 9, 22, HolidayRules.Citizens)]   // 敬老の日(21) 和 秋分の日(23) 中间
        [InlineData(2026, 5, 6, HolidayRules.Substitute)]  // 5/3 是周日，5/4、5/5 是祝日，顺延到 5/6
        [InlineData(2026, 11, 23, "勤労感謝の日")]
        [InlineData(2028, 1, 10, "成人の日")]              // CSV 之外，纯规则
        [InlineData(2032, 9, 21, HolidayRules.Citizens)]  // 敬老の日(20) 和 秋分の日(22) 中间
        [InlineData(2033, 3, 21, HolidayRules.Substitute)] // 春分 3/20 是周日
        [InlineData(1948, 11, 23, "勤労感謝の日")]         // 祝日法施行那年
        public void KnownHolidays(int y, int m, int d, string name)
        {
            var book = new HolidayBook(Official);
            Assert.Equal(name, book.NameOf(D(y, m, d)));
        }

        [Fact]
        public void NothingBeforeTheLaw()
        {
            Assert.Empty(HolidayRules.ForYear(1947));
            Assert.Equal(new[] { D(1948, 9, 23), D(1948, 11, 3), D(1948, 11, 23) },
                         HolidayRules.ForYear(1948).Keys.ToArray());
        }

        [Fact]
        public void BookPrefersOfficialAndRenamesGenericDays()
        {
            var book = new HolidayBook(Official);
            Assert.True(book.IsOfficial(2027));
            Assert.False(book.IsOfficial(2028));
            Assert.Equal(HolidayRules.Substitute, book.NameOf(D(2019, 5, 6)));
            Assert.Equal(HolidayRules.Citizens, book.NameOf(D(2019, 4, 30)));
            Assert.Equal("天皇の即位の日", book.NameOf(D(2019, 5, 1)));
            Assert.Null(book.NameOf(D(2026, 11, 13)));
        }

        [Fact]
        public void BookUsesCsvEvenWhenRulesWouldDiffer()
        {
            // 假设某年政府临时加了一天休日：CSV 里有、规则里没有，应以 CSV 为准
            var csv = new Dictionary<DateTime, string>(Official) { [D(2027, 6, 1)] = "休日" };
            var book = new HolidayBook(csv);
            Assert.Equal("休日", book.NameOf(D(2027, 6, 1)));
        }

        [Fact]
        public void NextHoliday()
        {
            var book = new HolidayBook(Official);
            var next = book.NextAfter(D(2026, 11, 13));
            Assert.NotNull(next);
            Assert.Equal(D(2026, 11, 23), next!.Value.Key);
            // 跨年
            Assert.Equal(D(2027, 1, 1), book.NextAfter(D(2026, 11, 23))!.Value.Key);
        }

        [Fact]
        public void InMonthListsInOrder()
        {
            var book = new HolidayBook(Official);
            var may = book.InMonth(2026, 5).Select(p => p.Key.Day).ToArray();
            Assert.Equal(new[] { 3, 4, 5, 6 }, may);
            Assert.Empty(book.InMonth(2026, 6));
        }

        [Fact]
        public void ParseCsvRejectsGarbage()
        {
            Assert.Throws<FormatException>(() => HolidayBook.ParseCsv(new byte[] { 0x3C, 0x68, 0x74, 0x6D, 0x6C, 0x3E }));
        }

        [Theory]
        [InlineData(2026, 11, 13, "令和8年")]
        [InlineData(2019, 5, 1, "令和元年")]
        [InlineData(2019, 4, 30, "平成31年")]
        [InlineData(1989, 1, 7, "昭和64年")]
        [InlineData(1989, 1, 8, "平成元年")]
        [InlineData(1900, 1, 1, "明治33年")]
        public void Wareki(int y, int m, int d, string expected)
        {
            Assert.Equal(expected, Core.Wareki.Format(D(y, m, d)));
        }
    }
}
