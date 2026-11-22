"""1000년 이전 음력 추정 (KASI 표가 없는 시기: 삼국·통일신라·고려 초).

옛 중국 역법의 큰 틀을 천문 계산으로 흉내 낸다. **추정값이다(verified=False).**
- 삭(달의 시작): 619년(당 무인력) 이전은 평삭(평균 삭망월), 이후는 정삭(실제 합삭, Meeus 49장).
- 절기: 평기(동지에서 1년을 24등분). 중국은 1645년까지 평기를 썼다.
- 동지가 든 달 = 11월. 동지~다음 동지 사이에 달이 13개면, 중기가 없는 첫 달이 윤달.
- 날짜 경계: 동경 120도 기준 시각(UT+8). 합삭이 하루의 0.8 뒤면 다음 날이 초하루(진삭).
- KASI 표(1001~1399년) 대조: 달 첫날 일치 약 90%, 나머지 대부분 ±1일, 윤달 위치가 다른 해 약 9%.
연도는 천문 연도(기원전 1년 = 0, 기원전 57년 = -56)를 쓴다.

정확도: KASI 표(1000~1400년)와 달 시작일을 대조한 값을 tests/test_ancient.py에 둔다.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from functools import lru_cache

SYNODIC = 29.530588861
TROPICAL = 365.2421897
TZ = 8 / 24  # UT+8
TRUE_NEWMOON_FROM = 619  # 이 해부터 정삭
ADVANCE = 0.8  # 진삭(進朔): 합삭이 그날의 이 비율 뒤면 다음 날을 초하루로(KASI 1000~1400년 대조로 고름)


def delta_t_days(year: float) -> float:
    """ΔT(TT−UT) 근사, Espenak–Meeus 다항식."""
    if year < 500:
        u = year / 100
        s = (10583.6 - 1014.41 * u + 33.78311 * u**2 - 5.952053 * u**3 - 0.1798452 * u**4
             + 0.022174192 * u**5 + 0.0090316521 * u**6)
    else:
        u = (year - 1000) / 100
        s = (1574.2 - 556.01 * u + 71.23472 * u**2 + 0.319781 * u**3 - 0.8503463 * u**4
             - 0.005050998 * u**5 + 0.0083572073 * u**6)
    return s / 86400


def _mean_newmoon_jde(k: int) -> float:
    t = k / 1236.85
    return 2451550.09766 + SYNODIC * k + 0.00015437 * t**2 - 0.000000150 * t**3 + 0.00000000073 * t**4


def _true_newmoon_jde(k: int) -> float:
    t = k / 1236.85
    r = math.radians
    e = 1 - 0.002516 * t - 0.0000074 * t**2
    m = r(2.5534 + 29.10535670 * k - 0.0000014 * t**2 - 0.00000011 * t**3)
    mp = r(201.5643 + 385.81693528 * k + 0.0107582 * t**2 + 0.00001238 * t**3 - 0.000000058 * t**4)
    f = r(160.7108 + 390.67050284 * k - 0.0016118 * t**2 - 0.00000227 * t**3 + 0.000000011 * t**4)
    om = r(124.7746 - 1.56375588 * k + 0.0020672 * t**2 + 0.00000215 * t**3)
    s = math.sin
    c = (-0.40720 * s(mp) + 0.17241 * e * s(m) + 0.01608 * s(2 * mp) + 0.01039 * s(2 * f)
         + 0.00739 * e * s(mp - m) - 0.00514 * e * s(mp + m) + 0.00208 * e * e * s(2 * m)
         - 0.00111 * s(mp - 2 * f) - 0.00057 * s(mp + 2 * f) + 0.00056 * e * s(2 * mp + m)
         - 0.00042 * s(3 * mp) + 0.00042 * e * s(m + 2 * f) + 0.00038 * e * s(m - 2 * f)
         - 0.00024 * e * s(2 * mp - m) - 0.00017 * s(om) - 0.00007 * s(mp + 2 * m)
         + 0.00004 * s(2 * mp - 2 * f) + 0.00004 * s(3 * m) + 0.00003 * s(mp + m - 2 * f)
         + 0.00003 * s(2 * mp + 2 * f) - 0.00003 * s(mp + m + 2 * f) + 0.00003 * s(mp - m + 2 * f)
         - 0.00002 * s(mp - m - 2 * f) - 0.00002 * s(3 * mp + m) + 0.00002 * s(4 * mp))
    return _mean_newmoon_jde(k) + c


def newmoon_day(k: int) -> int:
    """k번째 삭이 든 날의 JDN(UT+8 기준)."""
    approx_year = 2000 + k / 12.3685
    jde = _true_newmoon_jde(k) if approx_year >= TRUE_NEWMOON_FROM else _mean_newmoon_jde(k)
    x = jde - delta_t_days(approx_year) + TZ + 0.5
    day = math.floor(x)
    return day + 1 if x - day >= ADVANCE else day


def winter_solstice_jd(year: int) -> float:
    """그 해 12월 동지(평균값, Meeus 27장) — UT+8 기준 JD."""
    if year < 1000:
        y = year / 1000
        jde = 1721414.39987 + 365242.88257 * y - 0.00769 * y**2 - 0.00933 * y**3 - 0.00006 * y**4
    else:
        y = (year - 2000) / 1000
        jde = 2451900.05952 + 365242.74049 * y - 0.06223 * y**2 - 0.00823 * y**3 + 0.00032 * y**4
    return jde - delta_t_days(year) + TZ


def _k_near(jd: float) -> int:
    return math.floor((jd - 2451550.09766) / SYNODIC)


def _month11_start(year: int) -> int:
    """그 해 동지가 든 달(11월)의 첫날."""
    ws = math.floor(winter_solstice_jd(year) + 0.5)
    k = _k_near(ws) + 1
    while newmoon_day(k) > ws:
        k -= 1
    return k


@lru_cache(maxsize=4096)
def _cycle(year: int) -> tuple[tuple[int, int, bool, int], ...]:
    """(year-1)년 11월 ~ year년 10월(윤달 포함): (연, 월, 윤, 첫날 JDN)."""
    k0, k1 = _month11_start(year - 1), _month11_start(year)
    starts = [newmoon_day(k) for k in range(k0, k1 + 1)]
    n = k1 - k0
    ws0 = winter_solstice_jd(year - 1)
    step = TROPICAL / 12
    zq = [math.floor(ws0 + step * i + 0.5) for i in range(14)]  # 중기(평기)
    leap_i = None
    if n == 13:
        for i in range(n):
            if not any(starts[i] <= z < starts[i + 1] for z in zq):
                leap_i = i
                break
        if leap_i is None:
            leap_i = n - 1
    out = []
    m, y = 11, year - 1
    for i in range(n):
        if i == leap_i:
            out.append((y, m, True, starts[i]))
            continue
        if i > 0:
            m += 1
            if m == 13:
                m, y = 1, y + 1
        out.append((y, m, False, starts[i]))
    out.append((None, None, False, starts[n]))
    return tuple(out)


def _months_around(year: int):
    a, b = _cycle(year), _cycle(year + 1)
    return list(a[:-1]) + list(b)


def lunar_to_jdn(year: int, month: int, day: int, leap: bool = False) -> int:
    ms = _months_around(year)
    for i, (y, m, lp, st) in enumerate(ms[:-1]):
        if (y, m, lp) == (year, month, leap):
            n = ms[i + 1][3] - st
            if not 1 <= day <= n:
                raise ValueError(f"{year}년 {'윤' if leap else ''}{month}월은 {n}일까지(추정)")
            return st + day - 1
    raise ValueError(f"없는 음력 달(추정): {year}년 {'윤' if leap else ''}{month}월")


def month_range(year: int, month: int, leap: bool = False) -> tuple[int, int]:
    """그 달 첫날·끝날 JDN."""
    ms = _months_around(year)
    for i, (y, m, lp, st) in enumerate(ms[:-1]):
        if (y, m, lp) == (year, month, leap):
            return st, ms[i + 1][3] - 1
    raise ValueError(f"없는 음력 달(추정): {year}년 {'윤' if leap else ''}{month}월")


def year_range(year: int) -> tuple[int, int]:
    ms = [x for x in _months_around(year) if x[0] == year]
    s = ms[0][3]
    e = month_range(year, ms[-1][1], ms[-1][2])[1]
    return s, e


def jdn_to_lunar(jdn: int):
    """추정 음력 (연, 월, 일, 윤)."""
    from .calendar import jdn_to_solar
    y = jdn_to_solar(jdn).year
    for yy in (y, y - 1):
        ms = _months_around(yy)
        starts = [x[3] for x in ms]
        i = bisect_right(starts, jdn) - 1
        if 0 <= i < len(ms) - 1 and ms[i][0] is not None:
            return ms[i][0], ms[i][1], jdn - ms[i][3] + 1, ms[i][2]
    raise ValueError(jdn)
