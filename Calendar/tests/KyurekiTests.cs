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

        /// <summary>月表自体の整合性：各月は 29 日か 30 日。月番号は 1 ずつ増え、閏月は同じ番号の月のすぐ後に来る。</summary>
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
                    Assert.Equal(Math.Abs(prev), -cur);       // 閏 n 月は n 月の後に来る
                else
                    Assert.Equal(Math.Abs(prev) % 12 + 1, cur);
            }
        }

        [Fact]
        public void LeapMonthsAreRareEnough()
        {
            // 19 年 7 閏：201 年でおよそ 74 回
            int leaps = 0;
            for (int i = 0; i < Kyureki.MonthCount; i++)
                if (Kyureki.MonthNumber(i) < 0)
                    leaps++;
            Assert.InRange(leaps, 70, 78);
        }

        [Theory]
        [InlineData(2026, 2, 17, 1, false, 1)]     // 2026 年の旧正月
        [InlineData(2033, 12, 22, 11, true, 1)]    // 2033 年問題：通説どおり閏11月
        [InlineData(2023, 3, 22, 2, true, 1)]      // 2023 年の閏2月
        [InlineData(2017, 2, 26, 2, false, 1)]     // 朔が 23:58（日本時間）なので、その日が朔日
        [InlineData(2025, 7, 25, 6, true, 1)]      // 2025 年の閏6月
        public void KnownDates(int y, int m, int d, int month, bool leap, int day)
        {
            Assert.True(Kyureki.TryGetDate(D(y, m, d), out var k));
            Assert.Equal((month, leap, day), (k.Month, k.IsLeap, k.Day));
        }

        [Fact]
        public void RokuyoStartsFromSensho()
        {
            // 旧暦の各月の朔日の六曜は決まっている：1・7月は先勝、2・8月は友引、3・9月は先負、4・10月は仏滅、5・11月は大安、6・12月は赤口
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
            // 2026-02-17 は旧暦の正月朔日（先勝）。そこから順に循環する
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
