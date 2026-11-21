"""음력 ↔ JDN. 표: hdate/lunar_data.py (KASI 기반, 음력 1000~2050년)."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from .calendar import gregorian_to_jdn
from .lunar_data import BASE_YEAR, DATA

LAST_YEAR = BASE_YEAR + len(DATA) - 1
# 음력 1000-01-01. upstream은 이 날을 '1000-02-13'로 적는데, 이는 역산(proleptic) 그레고리력
# 기준이다(= 율리우스력 1000-02-08). 현대 기준일(음력 2024-01-01 = 2024-02-10)로 확인함.
_ANCHOR_JDN = gregorian_to_jdn(1000, 2, 13)


@dataclass(frozen=True, slots=True)
class LunarDate:
    year: int  # 음력 연도 (서력 번호)
    month: int  # 1~12
    day: int  # 1~30
    leap: bool = False  # 윤달 여부

    def __str__(self) -> str:
        return f"{self.year}년 {'윤' if self.leap else ''}{self.month}월 {self.day}일"


def _decode(v: int) -> list[tuple[int, bool, int]]:
    """연도 비트값 → [(월, 윤달?, 일수), ...] 실제 순서대로."""
    leap_month = (v >> 12) & 0xF
    months = []
    for m in range(1, 13):
        months.append((m, False, 30 if (v >> (12 - m)) & 1 else 29))
        if m == leap_month:
            months.append((m, True, 30 if (v >> 16) & 1 else 29))
    assert sum(x[2] for x in months) == (v >> 17) & 0x1FF
    return months


# 모든 음력 달의 시작 JDN 목록을 한 번만 만든다 (약 1.3만 개).
_MONTH_START: list[int] = []
_MONTH_INFO: list[tuple[int, int, bool, int]] = []  # (year, month, leap, length)
_INDEX: dict[tuple[int, int, bool], int] = {}


def _build() -> None:
    jdn = _ANCHOR_JDN
    for i, v in enumerate(DATA):
        y = BASE_YEAR + i
        for m, leap, n in _decode(v):
            _INDEX[(y, m, leap)] = len(_MONTH_START)
            _MONTH_START.append(jdn)
            _MONTH_INFO.append((y, m, leap, n))
            jdn += n
    _MONTH_START.append(jdn)  # 끝 경계


_build()
FIRST_JDN = _MONTH_START[0]
END_JDN = _MONTH_START[-1]  # 이 값 미만까지 지원


def month_length(year: int, month: int, leap: bool = False) -> int:
    i = _INDEX.get((year, month, leap))
    if i is None:
        raise ValueError(f"없는 음력 달: {year}년 {'윤' if leap else ''}{month}월")
    return _MONTH_INFO[i][3]


def leap_month_of(year: int) -> int | None:
    for m in range(1, 13):
        if (year, m, True) in _INDEX:
            return m
    return None


def lunar_to_jdn(year: int, month: int, day: int, leap: bool = False) -> int:
    i = _INDEX.get((year, month, leap))
    if i is None:
        raise ValueError(f"없는 음력 달: {year}년 {'윤' if leap else ''}{month}월")
    n = _MONTH_INFO[i][3]
    if not 1 <= day <= n:
        raise ValueError(f"{year}년 {'윤' if leap else ''}{month}월은 {n}일까지")
    return _MONTH_START[i] + day - 1


def month_start_jdn(year: int, month: int, leap: bool = False) -> int:
    return lunar_to_jdn(year, month, 1, leap)


def jdn_to_lunar(jdn: int) -> LunarDate:
    if not FIRST_JDN <= jdn < END_JDN:
        raise ValueError(f"JDN {jdn}: 음력 표 범위 밖")
    i = bisect_right(_MONTH_START, jdn) - 1
    y, m, leap, _ = _MONTH_INFO[i]
    return LunarDate(y, m, jdn - _MONTH_START[i] + 1, leap)
