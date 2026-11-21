"""양력(율리우스력/그레고리력) ↔ 율리우스적일(JDN, 정수).

규칙: JDN 2299161(= 1582-10-15 그레고리력) 이상은 그레고리력, 미만은 율리우스력.
"""
from __future__ import annotations

from dataclasses import dataclass

GREGORIAN_START_JDN = 2299161  # 1582-10-15 (그레고리력) = 1582-10-05 (율리우스력) 다음날


@dataclass(frozen=True, slots=True)
class SolarDate:
    year: int
    month: int
    day: int
    gregorian: bool  # True=그레고리력, False=율리우스력

    def iso(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    def __str__(self) -> str:
        return f"{self.iso()} ({'그레고리력' if self.gregorian else '율리우스력'})"


def gregorian_to_jdn(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def julian_to_jdn(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - 32083


def _jdn_to_ymd(jdn: int, gregorian: bool) -> tuple[int, int, int]:
    if gregorian:
        a = jdn + 32044
        b = (4 * a + 3) // 146097
        c = a - 146097 * b // 4
    else:
        b = 0
        c = jdn + 32082
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def jdn_to_solar(jdn: int) -> SolarDate:
    """규칙에 따라 그레고리력 또는 율리우스력 날짜를 돌려준다."""
    greg = jdn >= GREGORIAN_START_JDN
    return SolarDate(*_jdn_to_ymd(jdn, greg), gregorian=greg)


def solar_to_jdn(y: int, m: int, d: int) -> int:
    """규칙에 맞는 양력 날짜를 JDN으로. 1582-10-05~14는 존재하지 않으므로 ValueError."""
    if (y, m, d) >= (1582, 10, 15):
        jdn = gregorian_to_jdn(y, m, d)
    elif (y, m, d) <= (1582, 10, 4):
        jdn = julian_to_jdn(y, m, d)
    else:
        raise ValueError(f"{y}-{m:02d}-{d:02d}: 그레고리력 개력으로 없는 날짜")
    if jdn_to_solar(jdn) != SolarDate(y, m, d, jdn >= GREGORIAN_START_JDN):
        raise ValueError(f"잘못된 양력 날짜: {y}-{m}-{d}")
    return jdn
