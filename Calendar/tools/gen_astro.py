"""生成旧暦（天保暦方式）的月表和春分/秋分日，写成 src/Core/AstroTables.g.cs。

    .venv\\Scripts\\python tools\\gen_astro.py            生成
    .venv\\Scripts\\python tools\\gen_astro.py --check    生成 + 对照香港天文台农历表

原理
----
* 朔（新月）所在的那一天（日本时间）是每个月的初一。
* 中気（太阳视黄经 0°, 30°, ... 330°）决定月份：含冬至的月是 11 月，含春分的是 2 月……
* 两个「含冬至的月」之间如果有 13 个月，其中第一个不含中気的月是閏月（这个规则对 2033 年
  给出「閏11月」，和日本历法界 2015 年定下的结论一致）。

天文计算用 JPL DE440s 星历（skyfield），第一次运行会把约 30 MB 的星历下载到 tools/cache。

验证：同一套算法改用北京时间（UTC+8）就是中国农历的规则，结果应与香港天文台公布的
1901–2100 年农历表逐月一致。--check 会下载那 200 个年表（也缓存在 tools/cache）并比对。
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from skyfield import almanac
from skyfield.api import Loader
from skyfield.framelib import ecliptic_frame
from skyfield.nutationlib import iau2000b_radians

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / "cache"
OUT = ROOT / "src" / "Core" / "AstroTables.g.cs"

FIRST_YEAR, LAST_YEAR = 1900, 2100
# 往两边多算一些，保证 1900-01-01 和 2100-12-31 所在的「岁」都完整
SEARCH_FROM = (1897, 11, 1)
SEARCH_TO = (2102, 2, 1)

JST, CST = 9, 8


@dataclass(frozen=True)
class Month:
    start: dt.date          # 初一
    number: int             # 1..12
    leap: bool


def load_events():
    load = Loader(str(CACHE), verbose=False)
    ts = load.timescale()
    eph = load("de440s.bsp")
    earth, sun = eph["earth"], eph["sun"]
    t0, t1 = ts.utc(*SEARCH_FROM), ts.utc(*SEARCH_TO)

    phases = almanac.moon_phases(eph)
    times, values = almanac.find_discrete(t0, t1, phases)
    new_moons = [t.utc_datetime() for t, v in zip(times, values) if v == 0]

    def term_index(t):
        t._nutation_angles_radians = iau2000b_radians(t)
        _, lon, _ = earth.at(t).observe(sun).apparent().frame_latlon(ecliptic_frame)
        return (lon.degrees // 15).astype(int) % 24

    term_index.step_days = 5.0
    times, values = almanac.find_discrete(t0, t1, term_index)
    # values[i] 是越过之后的区间号，越过的经度 = values[i] * 15°
    terms = [(t.utc_datetime(), int(v) * 15) for t, v in zip(times, values)]
    return new_moons, terms


def local_date(moment: dt.datetime, tz_hours: int) -> dt.date:
    return (moment + dt.timedelta(hours=tz_hours)).date()


def chuuki_month(longitude: int) -> int:
    """中気的经度 -> 它所在的月份。春分(0°)=2月，冬至(270°)=11月，雨水(330°)=1月。"""
    return (longitude // 30 + 1) % 12 + 1


def build_months(new_moons, terms, tz_hours: int) -> tuple[list[Month], list[str]]:
    starts = [local_date(m, tz_hours) for m in new_moons]
    chuuki = [(local_date(t, tz_hours), chuuki_month(lon))
              for t, lon in terms if lon % 30 == 0]

    # 每个月含有哪些中気
    contains: list[list[int]] = [[] for _ in starts]
    j = 0
    for i in range(len(starts) - 1):
        while j < len(chuuki) and chuuki[j][0] < starts[i]:
            j += 1
        k = j
        while k < len(chuuki) and chuuki[k][0] < starts[i + 1]:
            contains[i].append(chuuki[k][1])
            k += 1

    winter = [i for i, c in enumerate(contains) if 11 in c]
    notes: list[str] = []
    numbered: dict[int, tuple[int, bool]] = {}
    for a, b in zip(winter, winter[1:]):
        span = b - a
        if span == 12:
            leap_at = None
            for i in range(a + 1, b):
                if not contains[i]:
                    notes.append(f"{starts[i]} 无中気但本岁只有 12 个月，不置閏")
        elif span == 13:
            leap_at = next((i for i in range(a + 1, b) if not contains[i]), None)
            if leap_at is None:
                raise SystemExit(f"{starts[a]} 起的岁有 13 个月却找不到无中気的月")
        else:
            raise SystemExit(f"{starts[a]} 起的岁有 {span} 个月")

        number = 11
        for i in range(a, b):
            if i == leap_at:
                numbered[i] = (number, True)
                continue
            if i != a:
                number = number % 12 + 1
            numbered[i] = (number, False)
            # 含中気的月，其月份必须和中気一致（两个中気的月只要含其一即可）
            if contains[i] and number not in contains[i]:
                notes.append(f"{starts[i]} 编为 {number} 月，但含的中気是 {contains[i]}")

    months = [Month(starts[i], *numbered[i]) for i in sorted(numbered)]
    return months, notes


def clip(months: list[Month]) -> list[Month]:
    """只留 1900-01-01 ~ 2100-12-31 用得到的月（含 1900-01-01 所在的那个月）。"""
    first = dt.date(FIRST_YEAR, 1, 1)
    last = dt.date(LAST_YEAR, 12, 31)
    begin = max(i for i, m in enumerate(months) if m.start <= first)
    end = max(i for i, m in enumerate(months) if m.start <= last)
    # 多留一个月当「结束哨兵」，查表时用来算最后一个月的长度
    return months[begin:end + 2]


def equinox_days(terms, tz_hours: int) -> tuple[list[int], list[int]]:
    spring: dict[int, int] = {}
    autumn: dict[int, int] = {}
    for moment, lon in terms:
        day = local_date(moment, tz_hours)
        if lon == 0:
            spring[day.year] = day.day
        elif lon == 180:
            autumn[day.year] = day.day
    years = range(FIRST_YEAR, LAST_YEAR + 1)
    return [spring[y] for y in years], [autumn[y] for y in years]


def near_midnight(new_moons, terms, tz_hours: int, minutes: int) -> list[str]:
    """离日界线太近的朔和中気：ΔT 或星历的微小误差就可能让它落到另一天。"""
    out = []
    events = [("朔", m) for m in new_moons] + [
        (f"中気{lon}°", t) for t, lon in terms if lon % 30 == 0]
    for name, moment in events:
        local = moment + dt.timedelta(hours=tz_hours)
        if not FIRST_YEAR <= local.year <= LAST_YEAR:
            continue
        since = local.hour * 60 + local.minute + local.second / 60
        gap = min(since, 1440 - since)
        if gap < minutes:
            out.append(f"{local:%Y-%m-%d %H:%M:%S} {name}")
    return out


def print_sensitivity(new_moons, terms, months: list[Month], seconds: int = 60) -> None:
    """把所有事件整体挪 ±seconds 秒重算：会变的月份就是「对 ΔT 敏感」的。

    未来的 ΔT（地球自转减慢量）只能预测，到 2100 年可能差上一两分钟。
    """
    base = set(months)
    window = (dt.date(FIRST_YEAR, 1, 1), dt.date(LAST_YEAR, 12, 31))
    changed: set[Month] = set()
    for moon_shift in (-seconds, 0, seconds):
        for term_shift in (-seconds, 0, seconds):
            if moon_shift == term_shift == 0:
                continue
            shifted, _ = build_months(
                [m + dt.timedelta(seconds=moon_shift) for m in new_moons],
                [(t + dt.timedelta(seconds=term_shift), lon) for t, lon in terms], JST)
            changed |= {m for m in base - set(shifted)
                        if window[0] <= m.start <= window[1]}
    if changed:
        print(f"事件时刻挪 ±{seconds} 秒会改变的月（这些月的六曜有不确定性）:")
        for m in sorted(changed, key=lambda m: m.start):
            print("  ", m)
    else:
        print(f"事件时刻挪 ±{seconds} 秒，表一个月都不变")


# --------------------------------------------------------------------------
# 输出 C#
# --------------------------------------------------------------------------

def rows(values, per_line: int) -> str:
    lines = []
    for i in range(0, len(values), per_line):
        lines.append("            " + ", ".join(str(v) for v in values[i:i + per_line]) + ",")
    return "\n".join(lines)


def write_cs(months: list[Month], spring: list[int], autumn: list[int]) -> None:
    starts = [int(m.start.strftime("%Y%m%d")) for m in months]
    numbers = [-m.number if m.leap else m.number for m in months]
    text = f"""// <auto-generated>
// 由 tools/gen_astro.py 生成（JPL DE440s 星历，日本时间 UTC+9），不要手改。
// </auto-generated>

namespace KKCalendar.Core
{{
    internal static class AstroTables
    {{
        public const int FirstYear = {FIRST_YEAR};
        public const int LastYear = {LAST_YEAR};

        /// <summary>旧暦每个月初一的公历日期（yyyymmdd）。最后一项是哨兵，只用来算前一个月的长度。</summary>
        public static readonly int[] MonthStarts =
        {{
{rows(starts, 8)}
        }};

        /// <summary>与 MonthStarts 一一对应的月份，閏月为负数。</summary>
        public static readonly sbyte[] MonthNumbers =
        {{
{rows(numbers, 24)}
        }};

        /// <summary>春分日（3 月的第几天），下标 = 年 - FirstYear。</summary>
        public static readonly byte[] VernalEquinoxDay =
        {{
{rows(spring, 25)}
        }};

        /// <summary>秋分日（9 月的第几天），下标 = 年 - FirstYear。</summary>
        public static readonly byte[] AutumnalEquinoxDay =
        {{
{rows(autumn, 25)}
        }};
    }}
}}
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\r\n")


# --------------------------------------------------------------------------
# 对照香港天文台
# --------------------------------------------------------------------------

_CN_MONTH = {"正": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
             "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}


def hko_months() -> list[Month]:
    folder = CACHE / "hko"
    folder.mkdir(parents=True, exist_ok=True)
    months = []
    for year in range(1901, 2101):
        path = folder / f"T{year}c.txt"
        if not path.exists():
            url = f"https://www.hko.gov.hk/tc/gts/time/calendar/text/files/T{year}c.txt"
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                path.write_bytes(response.read())
            time.sleep(0.2)
        for line in path.read_text(encoding="utf-8-sig").splitlines()[3:]:
            parts = line.split()
            if len(parts) < 2 or not parts[1].endswith("月"):
                continue
            ymd = parts[0].replace("年", "-").replace("月", "-").replace("日", "")
            y, m, d = (int(x) for x in ymd.split("-"))
            name = parts[1][:-1]
            leap = name.startswith("閏")
            months.append(Month(dt.date(y, m, d), _CN_MONTH[name.lstrip("閏")], leap))
    return months


def check_against_hko(cst_months: list[Month]) -> int:
    reference = hko_months()
    lo, hi = reference[0].start, reference[-1].start
    ours = [m for m in cst_months if lo <= m.start <= hi]
    if ours == reference:
        print(f"香港天文台对照：{len(reference)} 个月（{lo} ~ {hi}）全部一致")
        return 0
    ref_set, our_set = set(reference), set(ours)
    print("香港天文台对照：有出入")
    for m in sorted(ref_set - our_set, key=lambda m: m.start):
        print("  HKO 有、我们没有:", m)
    for m in sorted(our_set - ref_set, key=lambda m: m.start):
        print("  我们有、HKO 没有:", m)
    return 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")     # 日文 Windows 的控制台默认是 cp932
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="对照香港天文台农历表")
    args = parser.parse_args()

    new_moons, terms = load_events()
    jst_months, notes = build_months(new_moons, terms, JST)
    for note in notes:
        print("注意:", note)
    table = clip(jst_months)
    spring, autumn = equinox_days(terms, JST)
    write_cs(table, spring, autumn)
    leaps = [m for m in table if m.leap]
    print(f"写出 {OUT.relative_to(ROOT)}：{len(table) - 1} 个月，其中閏月 {len(leaps)} 个，"
          f"{table[0].start} ~ {table[-1].start}")

    close = near_midnight(new_moons, terms, JST, 2)
    if close:
        print("离日本时间 0 点不到 2 分钟的朔/中気:")
        for line in close:
            print("  ", line)
    print_sensitivity(new_moons, terms, jst_months)

    status = 0
    if args.check:
        cst_months, cst_notes = build_months(new_moons, terms, CST)
        for note in cst_notes:
            print("北京时间注意:", note)
        status = check_against_hko(cst_months)
        print("离北京时间 0 点不到 2 分钟的朔/中気:")
        for line in near_midnight(new_moons, terms, CST, 2):
            print("  ", line)
        jst_set = set(jst_months)
        diff = [m for m in cst_months
                if dt.date(FIRST_YEAR, 1, 1) <= m.start <= dt.date(LAST_YEAR, 12, 31)
                and m not in jst_set]
        print(f"日本旧暦与中国农历月首不同的月：{len(diff)} 个（时差 1 小时造成，属正常）")
    return status


if __name__ == "__main__":
    sys.exit(main())
