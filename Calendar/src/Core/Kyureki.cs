using System;

namespace KKCalendar.Core
{
    /// <summary>旧暦の月と日。</summary>
    public readonly struct KyurekiDate
    {
        public KyurekiDate(int month, bool leap, int day)
        {
            Month = month;
            IsLeap = leap;
            Day = day;
        }

        public int Month { get; }
        public bool IsLeap { get; }
        public int Day { get; }

        public override string ToString() => (IsLeap ? "閏" : "") + Month + "月" + Day + "日";
    }

    /// <summary>
    /// 旧暦と六曜。tools/gen_astro.py が JPL の暦であらかじめ計算した月表（1900–2100）を引く。
    /// </summary>
    public static class Kyureki
    {
        /// <summary>六曜は (旧暦月 + 旧暦日) mod 6 の順に並ぶ：旧暦の正月朔日が先勝。</summary>
        static readonly string[] RokuyoNames = { "大安", "赤口", "先勝", "友引", "先負", "仏滅" };

        static readonly DateTime[] Starts = BuildStarts();

        static DateTime[] BuildStarts()
        {
            var starts = new DateTime[AstroTables.MonthStarts.Length];
            for (int i = 0; i < starts.Length; i++)
            {
                int v = AstroTables.MonthStarts[i];
                starts[i] = new DateTime(v / 10000, v / 100 % 100, v % 100);
            }
            return starts;
        }

        /// <summary>表でカバーできる範囲（両端を含む）。</summary>
        public static DateTime MinDate => Starts[0];
        public static DateTime MaxDate => Starts[Starts.Length - 1].AddDays(-1);

        public static bool TryGetDate(DateTime date, out KyurekiDate result)
        {
            date = date.Date;
            result = default;
            if (date < MinDate || date > MaxDate)
                return false;

            // 最後の要素は番兵。Starts[i] <= date < Starts[i + 1] となる i を探す
            int lo = 0, hi = Starts.Length - 2;
            while (lo < hi)
            {
                int mid = (lo + hi + 1) / 2;
                if (Starts[mid] <= date)
                    lo = mid;
                else
                    hi = mid - 1;
            }
            int number = AstroTables.MonthNumbers[lo];
            result = new KyurekiDate(Math.Abs(number), number < 0, (date - Starts[lo]).Days + 1);
            return true;
        }

        public static string? Rokuyo(DateTime date)
        {
            if (!TryGetDate(date, out var k))
                return null;
            return RokuyoNames[(k.Month + k.Day) % 6];
        }

        /// <summary>テスト用：旧暦で index 番目の月の朔日と月番号（閏月は負）。</summary>
        internal static int MonthCount => Starts.Length - 1;
        internal static DateTime MonthStart(int index) => Starts[index];
        internal static int MonthNumber(int index) => AstroTables.MonthNumbers[index];
    }
}
