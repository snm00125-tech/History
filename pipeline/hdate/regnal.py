"""왕력(조선 국왕 재위년) ↔ 음력 연도.

칭원법
- 유년칭원(踰年稱元): 즉위한 해는 '즉위년', 다음 해가 1년. 조선 대부분의 국왕.
- 즉위년칭원: 즉위한 해가 곧 1년. 태조·세조·중종·인조(반정·선양 즉위).

주의: 아래 표의 원년과 칭원법은 일반 연표 지식으로 넣었고, 선조만 검증 예시로 확인했다
(verified=True). 나머지는 실록 기사 머리(예: '선조 25년 임진 4월 13일')와 대조해 확정한다.
즉위일(accession)은 아직 비어 있다. 실록 즉위년 첫 기사에서 채운다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .lunar import LunarDate


@dataclass(frozen=True, slots=True)
class Reign:
    king: str
    first_year: int  # 재위 1년의 음력 연도
    accession_year_is_first: bool = False  # True면 즉위년칭원 (즉위년 없음)
    accession: LunarDate | None = None  # 즉위일 (음력). 미확정이면 None
    verified: bool = False


JOSEON: tuple[Reign, ...] = (
    Reign("태조", 1392, True),
    Reign("정종", 1399),
    Reign("태종", 1401),
    Reign("세종", 1419),
    Reign("문종", 1451),
    Reign("단종", 1453),
    Reign("세조", 1455, True),
    Reign("예종", 1469),
    Reign("성종", 1470),
    Reign("연산군", 1495),
    Reign("중종", 1506, True),
    Reign("인종", 1545),
    Reign("명종", 1546),
    Reign("선조", 1568, verified=True),
    Reign("광해군", 1609),
    Reign("인조", 1623, True),
    Reign("효종", 1650),
    Reign("현종", 1660),
    Reign("숙종", 1675),
    Reign("경종", 1721),
    Reign("영조", 1725),
    Reign("정조", 1777),
    Reign("순조", 1801),
    Reign("헌종", 1835),
    Reign("철종", 1850),
    Reign("고종", 1864),
)
_BY_KING = {r.king: r for r in JOSEON}


@dataclass(frozen=True, slots=True)
class RegnalYear:
    king: str
    year: int  # 0 = 즉위년
    ambiguous: bool = False  # 즉위일 미확정으로 앞 왕/뒤 왕 판정을 못 한 경우

    def __str__(self) -> str:
        y = "즉위년" if self.year == 0 else f"{self.year}년"
        return f"{self.king} {y}" + (" (즉위일 미확정)" if self.ambiguous else "")


def to_lunar_year(king: str, year: int) -> int:
    """(왕, 재위년) → 음력 연도. year=0은 즉위년."""
    r = _BY_KING.get(king)
    if r is None:
        raise ValueError(f"왕력 표에 없는 왕: {king}")
    if year == 0:
        if r.accession_year_is_first:
            raise ValueError(f"{king}은 즉위년칭원이라 '즉위년'이 없음")
        return r.first_year - 1
    if year < 0:
        raise ValueError("재위년은 0 이상")
    return r.first_year + year - 1


def _accession_year(r: Reign) -> int:
    return r.first_year if r.accession_year_is_first else r.first_year - 1


def from_lunar(d: LunarDate) -> RegnalYear | None:
    """음력 날짜 → 왕력. 표 범위 밖이면 None."""
    idx = None
    for i, r in enumerate(JOSEON):
        if _accession_year(r) <= d.year:
            idx = i
    if idx is None:
        return None
    r = JOSEON[idx]
    ambiguous = False
    if d.year == _accession_year(r) and idx > 0:
        # 즉위한 해: 즉위일 전이면 앞 왕
        if r.accession is None:
            ambiguous = True
            prev = JOSEON[idx - 1]
            return RegnalYear(prev.king, d.year - prev.first_year + 1, ambiguous=True)
        key = lambda x: (x.month + (0.5 if x.leap else 0), x.day)
        if key(d) < key(r.accession):
            prev = JOSEON[idx - 1]
            return RegnalYear(prev.king, d.year - prev.first_year + 1)
    return RegnalYear(r.king, d.year - r.first_year + 1, ambiguous)


def reign(king: str) -> Reign:
    return _BY_KING[king]
