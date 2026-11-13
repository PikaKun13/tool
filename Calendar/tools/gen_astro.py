"""旧暦（天保暦方式）の月表と春分・秋分の日を生成し、src/Core/AstroTables.g.cs に書き出す。

    .venv\\Scripts\\python tools\\gen_astro.py            生成
    .venv\\Scripts\\python tools\\gen_astro.py --check    生成 + 香港天文台の農暦表と照合

原理
----
* 朔（新月）のある日（日本時間）が各月の朔日（1 日）。
* 中気（太陽の視黄経 0°, 30°, ... 330°）で月の番号が決まる：冬至を含む月が 11 月、春分を含む月が 2 月……
* 「冬至を含む月」から次の「冬至を含む月」までが 13 か月なら、そのうち最初の中気を含まない月が閏月
  （この規則は 2033 年について「閏11月」を与え、日本の暦学界が 2015 年に出した結論と一致する）。

天文計算には JPL DE440s 暦（skyfield）を使う。初回実行時に約 30 MB の暦データを tools/cache にダウンロードする。

検証：同じアルゴリズムを北京時間（UTC+8）に切り替えると中国の農暦のルールになるので、結果は香港天文台が公開している
1901–2100 年の農暦表と月ごとに一致するはず。--check はその 200 年分の年表をダウンロードし（これも tools/cache にキャッシュ）、照合する。
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
# 両側に少し余分に計算して、1900-01-01 と 2100-12-31 を含む「歳」が欠けないようにする
SEARCH_FROM = (1897, 11, 1)
SEARCH_TO = (2102, 2, 1)

JST, CST = 9, 8


@dataclass(frozen=True)
class Month:
    start: dt.date          # 朔日
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
    # values[i] は越えたあとの区間番号。越えた経度 = values[i] * 15°
    terms = [(t.utc_datetime(), int(v) * 15) for t, v in zip(times, values)]
    return new_moons, terms


def local_date(moment: dt.datetime, tz_hours: int) -> dt.date:
    return (moment + dt.timedelta(hours=tz_hours)).date()


def chuuki_month(longitude: int) -> int:
    """中気の経度 -> その中気を含む月の番号。春分(0°)=2月、冬至(270°)=11月、雨水(330°)=1月。"""
    return (longitude // 30 + 1) % 12 + 1


def build_months(new_moons, terms, tz_hours: int) -> tuple[list[Month], list[str]]:
    starts = [local_date(m, tz_hours) for m in new_moons]
    chuuki = [(local_date(t, tz_hours), chuuki_month(lon))
              for t, lon in terms if lon % 30 == 0]

    # 各月がどの中気を含むか
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
                    notes.append(f"{starts[i]} は中気を含まないが、この歳は 12 か月しかないので閏月にしない")
        elif span == 13:
            leap_at = next((i for i in range(a + 1, b) if not contains[i]), None)
            if leap_at is None:
                raise SystemExit(f"{starts[a]} から始まる歳は 13 か月あるのに、中気を含まない月が見つからない")
        else:
            raise SystemExit(f"{starts[a]} から始まる歳が {span} か月ある")

        number = 11
        for i in range(a, b):
            if i == leap_at:
                numbered[i] = (number, True)
                continue
            if i != a:
                number = number % 12 + 1
            numbered[i] = (number, False)
            # 中気を含む月は、月番号がその中気と一致しなければならない（中気を 2 つ含む月はどちらか一方と一致すればよい）
            if contains[i] and number not in contains[i]:
                notes.append(f"{starts[i]} を {number} 月としたが、含む中気は {contains[i]}")

    months = [Month(starts[i], *numbered[i]) for i in sorted(numbered)]
    return months, notes


def clip(months: list[Month]) -> list[Month]:
    """1900-01-01 〜 2100-12-31 で使う月だけを残す（1900-01-01 を含む月も含める）。"""
    first = dt.date(FIRST_YEAR, 1, 1)
    last = dt.date(LAST_YEAR, 12, 31)
    begin = max(i for i, m in enumerate(months) if m.start <= first)
    end = max(i for i, m in enumerate(months) if m.start <= last)
    # 「終端の番兵」としてもう 1 か月残す。表引きで最後の月の長さを求めるのに使う
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
    """日付の境目に近すぎる朔と中気：ΔT や暦のわずかな誤差で別の日になりうる。"""
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
    """すべてのイベントの時刻をまとめて ±seconds 秒ずらして再計算する：結果が変わる月が「ΔT に敏感」な月。

    将来の ΔT（地球の自転の遅れ）は予測するしかなく、2100 年には 1〜2 分ずれる可能性がある。
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
        print(f"イベント時刻を ±{seconds} 秒ずらすと変わる月（これらの月の六曜には不確かさがある）:")
        for m in sorted(changed, key=lambda m: m.start):
            print("  ", m)
    else:
        print(f"イベント時刻を ±{seconds} 秒ずらしても、表は 1 か月も変わらない")


# --------------------------------------------------------------------------
# C# の出力
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
// tools/gen_astro.py が生成（JPL DE440s 暦、日本時間 UTC+9）。手で編集しないこと。
// </auto-generated>

namespace KKCalendar.Core
{{
    internal static class AstroTables
    {{
        public const int FirstYear = {FIRST_YEAR};
        public const int LastYear = {LAST_YEAR};

        /// <summary>旧暦の各月の朔日の西暦日付（yyyymmdd）。最後の要素は番兵で、直前の月の長さを求めるためだけに使う。</summary>
        public static readonly int[] MonthStarts =
        {{
{rows(starts, 8)}
        }};

        /// <summary>MonthStarts と 1 対 1 で対応する月番号。閏月は負数。</summary>
        public static readonly sbyte[] MonthNumbers =
        {{
{rows(numbers, 24)}
        }};

        /// <summary>春分日（3 月の何日か）。添字 = 年 - FirstYear。</summary>
        public static readonly byte[] VernalEquinoxDay =
        {{
{rows(spring, 25)}
        }};

        /// <summary>秋分日（9 月の何日か）。添字 = 年 - FirstYear。</summary>
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
# 香港天文台との照合
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
        print(f"香港天文台との照合：{len(reference)} か月（{lo} 〜 {hi}）すべて一致")
        return 0
    ref_set, our_set = set(reference), set(ours)
    print("香港天文台との照合：食い違いあり")
    for m in sorted(ref_set - our_set, key=lambda m: m.start):
        print("  HKO にあってこちらにない:", m)
    for m in sorted(our_set - ref_set, key=lambda m: m.start):
        print("  こちらにあって HKO にない:", m)
    return 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")     # 日本語版 Windows のコンソールは既定で cp932
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="香港天文台の農暦表と照合する")
    args = parser.parse_args()

    new_moons, terms = load_events()
    jst_months, notes = build_months(new_moons, terms, JST)
    for note in notes:
        print("注意:", note)
    table = clip(jst_months)
    spring, autumn = equinox_days(terms, JST)
    write_cs(table, spring, autumn)
    leaps = [m for m in table if m.leap]
    print(f"{OUT.relative_to(ROOT)} に書き出し：{len(table) - 1} か月（うち閏月 {len(leaps)} か月）、"
          f"{table[0].start} ~ {table[-1].start}")

    close = near_midnight(new_moons, terms, JST, 2)
    if close:
        print("日本時間の 0 時から 2 分以内の朔/中気:")
        for line in close:
            print("  ", line)
    print_sensitivity(new_moons, terms, jst_months)

    status = 0
    if args.check:
        cst_months, cst_notes = build_months(new_moons, terms, CST)
        for note in cst_notes:
            print("北京時間での注意:", note)
        status = check_against_hko(cst_months)
        print("北京時間の 0 時から 2 分以内の朔/中気:")
        for line in near_midnight(new_moons, terms, CST, 2):
            print("  ", line)
        jst_set = set(jst_months)
        diff = [m for m in cst_months
                if dt.date(FIRST_YEAR, 1, 1) <= m.start <= dt.date(LAST_YEAR, 12, 31)
                and m not in jst_set]
        print(f"日本の旧暦と中国の農暦で月の始まりが違う月：{len(diff)} か月（1 時間の時差によるもので、正常）")
    return status


if __name__ == "__main__":
    sys.exit(main())
