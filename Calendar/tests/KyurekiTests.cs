using System;
using KKCalendar.Core;
using Xunit;

namespace KKCalendar.Tests
{
    public class KyurekiTests
    {
        static DateTime D(int y, int m, int d) => new DateTime(y, m, d);

        [Fact]
        public void TableCoversCalendarRange()
        {
            Assert.True(Kyureki.MinDate <= D(1900, 1, 1));
            Assert.True(Kyureki.MaxDate >= D(2100, 12, 31));
        }

        /// <summary>月表自身的一致性：每月 29 或 30 天；月份依次 +1，閏月紧跟同号的月。</summary>
        [Fact]
        public void TableIsConsistent()
        {
            for (int i = 0; i < Kyureki.MonthCount; i++)
            {
                int length = (Kyureki.MonthStart(i + 1) - Kyureki.MonthStart(i)).Days;
                Assert.InRange(length, 29, 30);
                if (i == 0)
                    continue;
                int prev = Kyureki.MonthNumber(i - 1), cur = Kyureki.MonthNumber(i);
                if (cur < 0)
                    Assert.Equal(Math.Abs(prev), -cur);       // 閏 n 月跟在 n 月后面
                else
                    Assert.Equal(Math.Abs(prev) % 12 + 1, cur);
            }
        }

        [Fact]
        public void LeapMonthsAreRareEnough()
        {
            // 19 年 7 閏：201 年里大约 74 个
            int leaps = 0;
            for (int i = 0; i < Kyureki.MonthCount; i++)
                if (Kyureki.MonthNumber(i) < 0)
                    leaps++;
            Assert.InRange(leaps, 70, 78);
        }

        [Theory]
        [InlineData(2026, 2, 17, 1, false, 1)]     // 2026 年旧正月
        [InlineData(2033, 12, 22, 11, true, 1)]    // 2033 年问题：按通行结论是閏11月
        [InlineData(2023, 3, 22, 2, true, 1)]      // 2023 年閏2月
        [InlineData(2017, 2, 26, 2, false, 1)]     // 朔在 23:58（日本时间），当天就是初一
        [InlineData(2025, 7, 25, 6, true, 1)]      // 2025 年閏6月
        public void KnownDates(int y, int m, int d, int month, bool leap, int day)
        {
            Assert.True(Kyureki.TryGetDate(D(y, m, d), out var k));
            Assert.Equal((month, leap, day), (k.Month, k.IsLeap, k.Day));
        }

        [Fact]
        public void RokuyoStartsFromSensho()
        {
            // 旧暦每个月初一的六曜是固定的：1・7月先勝、2・8月友引、3・9月先負、4・10月仏滅、5・11月大安、6・12月赤口
            string[] firstDay = { "", "先勝", "友引", "先負", "仏滅", "大安", "赤口",
                                  "先勝", "友引", "先負", "仏滅", "大安", "赤口" };
            for (int i = 0; i < Kyureki.MonthCount; i++)
            {
                var start = Kyureki.MonthStart(i);
                if (start < Kyureki.MinDate)
                    continue;
                Assert.Equal(firstDay[Math.Abs(Kyureki.MonthNumber(i))], Kyureki.Rokuyo(start));
            }
        }

        [Fact]
        public void RokuyoCyclesWithinAMonth()
        {
            string[] order = { "先勝", "友引", "先負", "仏滅", "大安", "赤口" };
            // 2026-02-17 是旧暦正月初一（先勝），之后按顺序循环
            for (int i = 0; i < 29; i++)
                Assert.Equal(order[i % 6], Kyureki.Rokuyo(D(2026, 2, 17).AddDays(i)));
        }

        [Fact]
        public void OutOfRangeIsNull()
        {
            Assert.Null(Kyureki.Rokuyo(D(1850, 1, 1)));
            Assert.Null(Kyureki.Rokuyo(D(2150, 1, 1)));
        }
    }
}
