"""왕력(조선 국왕 재위년) ↔ 음력 연도.

칭원법
- 유년칭원(踰年稱元): 즉위한 해는 '즉위년', 다음 해가 1년. 조선 대부분의 국왕.
- 즉위년칭원: 즉위한 해가 곧 1년. 태조·세조·중종·인조(반정·선양 즉위).
- 정종·태종·인종은 유년칭원이지만 실록에 '즉위년'이 없다. 즉위한 해 전체가 앞 왕의 마지막 해로 적혀 있다.

경계(boundary): 즉위일이 아니라 **그 왕 실록의 첫 날짜 기사**다(실록 원문 XML에서 추출,
tests/test_regnal_data.py가 원자료와 대조). 첫 기사가 앞 왕 훙서일인 경우가 많아 공식 즉위일과
며칠 다를 수 있다. 앞 왕 실록의 마지막 기사(sillok_last)와 겹치는 며칠은 labels_for()가 두 왕력을 모두 준다.

검증(verified=True): 원년·칭원법·경계를 실록 원문(공공데이터포털 15053647)의 연도 머리
'재위연도'와 기사 날짜로 확인함. 고종은 이 자료에 없어 미검증.
"""
from __future__ import annotations

from dataclasses import dataclass

from .lunar import LunarDate


@dataclass(frozen=True, slots=True)
class Reign:
    king: str
    first_year: int  # 재위 1년의 음력 연도
    accession_year_is_first: bool = False  # True면 즉위년칭원
    has_accession_year_label: bool = True  # 실록에 '즉위년' 표기가 있는가
    boundary: LunarDate | None = None  # 이 왕 실록 첫 날짜 기사 (이날부터 이 왕의 왕력)
    sillok_last: LunarDate | None = None  # 이 왕 실록 마지막 날짜 기사
    book: str | None = None  # 실록 ID (원문 XML)
    aliases: tuple[str, ...] = ()
    verified: bool = False


L = LunarDate
JOSEON: tuple[Reign, ...] = (
    Reign("태조", 1392, True, True, L(1392, 7, 17), L(1398, 12, 29), "waa", verified=True),
    Reign("정종", 1399, False, False, L(1399, 1, 1), L(1400, 12, 22), "wba", verified=True),
    Reign("태종", 1401, False, False, L(1401, 1, 1), L(1418, 11, 8), "wca", verified=True),
    Reign("세종", 1419, False, True, L(1418, 8, 11), L(1450, 2, 22), "wda", verified=True),
    Reign("문종", 1451, False, True, L(1450, 2, 18), L(1452, 9, 1), "wea", verified=True),
    Reign("단종", 1453, False, True, L(1452, 5, 14), L(1455, 6, 10, True), "wfa", verified=True),
    Reign("세조", 1455, True, True, L(1455, 6, 11, True), L(1468, 11, 28), "wga", verified=True),
    Reign("예종", 1469, False, True, L(1468, 9, 7), L(1469, 12, 18), "wha", verified=True),
    Reign("성종", 1470, False, True, L(1469, 11, 28), L(1494, 12, 24), "wia", verified=True),
    Reign("연산군", 1495, False, True, L(1494, 12, 25), L(1506, 9, 2), "wja", ("연산",), verified=True),
    Reign("중종", 1506, True, True, L(1506, 9, 2), L(1544, 12, 30), "wka", verified=True),
    Reign("인종", 1545, False, False, L(1545, 1, 1), L(1545, 7, 6), "wla", verified=True),
    Reign("명종", 1546, False, True, L(1545, 7, 7), L(1567, 6, 28), "wma", verified=True),
    Reign("선조", 1568, False, True, L(1567, 7, 4), L(1608, 2, 1), "wna", verified=True),
    Reign("광해군", 1609, False, True, L(1608, 2, 1), L(1623, 3, 23), "woa", ("광해",), verified=True),
    Reign("인조", 1623, True, True, L(1623, 3, 13), L(1649, 5, 8), "wpa", verified=True),
    Reign("효종", 1650, False, True, L(1649, 5, 8), L(1659, 5, 9), "wqa", verified=True),
    Reign("현종", 1660, False, True, L(1659, 5, 4), L(1674, 8, 18), "wra", verified=True),
    Reign("숙종", 1675, False, True, L(1674, 8, 18), L(1720, 6, 13), "wsa", verified=True),
    Reign("경종", 1721, False, True, L(1720, 6, 8), L(1724, 9, 3), "wta", verified=True),
    Reign("영조", 1725, False, True, L(1724, 8, 30), L(1776, 3, 10), "wua", verified=True),
    Reign("정조", 1777, False, True, L(1776, 3, 10), L(1800, 7, 15), "wva", verified=True),
    Reign("순조", 1801, False, True, L(1800, 7, 4), L(1834, 11, 18), "wwa", verified=True),
    Reign("헌종", 1835, False, True, L(1834, 11, 18), L(1849, 6, 9), "wxa", verified=True),
    Reign("철종", 1850, False, True, L(1849, 6, 9), L(1863, 12, 8), "wya", verified=True),
    Reign("고종", 1864),  # 이 자료에 없음(고순종실록은 별도 데이터셋 15053646). 미검증
)
_BY_KING = {n: r for r in JOSEON for n in (r.king, *r.aliases)}


@dataclass(frozen=True, slots=True)
class RegnalYear:
    king: str
    year: int  # 0 = 즉위년
    ambiguous: bool = False  # 경계를 몰라 앞 왕/뒤 왕 판정을 못 한 경우

    def __str__(self) -> str:
        y = "즉위년" if self.year == 0 else f"{self.year}년"
        return f"{self.king} {y}" + (" (경계 미확정)" if self.ambiguous else "")


def _key(d: LunarDate) -> tuple:
    return (d.year, d.month, int(d.leap), d.day)


def reign(king: str) -> Reign:
    r = _BY_KING.get(king)
    if r is None:
        raise ValueError(f"왕력 표에 없는 왕: {king}")
    return r


def to_lunar_year(king: str, year: int) -> int:
    """(왕, 재위년) → 음력 연도. year=0은 즉위년."""
    r = reign(king)
    if year == 0:
        if r.accession_year_is_first:
            raise ValueError(f"{r.king}은 즉위년칭원이라 '즉위년'이 없음")
        if not r.has_accession_year_label:
            raise ValueError(f"{r.king}은 실록에 '즉위년' 표기가 없음 (앞 왕의 마지막 해로 적힘)")
        return r.first_year - 1
    if year < 0:
        raise ValueError("재위년은 0 이상")
    return r.first_year + year - 1


def _label(r: Reign, d: LunarDate, ambiguous: bool = False) -> RegnalYear:
    return RegnalYear(r.king, d.year - r.first_year + 1, ambiguous)


def from_lunar(d: LunarDate) -> RegnalYear | None:
    """음력 날짜 → 대표 왕력(경계일부터 새 왕). 표 범위 밖이면 None."""
    if _key(d) < _key(JOSEON[0].boundary):
        return None
    for i in range(len(JOSEON) - 1, -1, -1):
        r = JOSEON[i]
        if r.boundary is not None:
            if _key(d) >= _key(r.boundary):
                return _label(r, d)
            continue
        # 경계 미상(고종): 앞 왕 실록 마지막 해 이후로만 판정
        prev = JOSEON[i - 1]
        if d.year >= r.first_year:
            return _label(r, d)
        if d.year == r.first_year - 1 and prev.sillok_last and _key(d) > _key(prev.sillok_last):
            return _label(prev, d, ambiguous=True)
    return None


def labels_for(d: LunarDate) -> list[RegnalYear]:
    """그 날짜를 다루는 모든 실록의 왕력 (교체기 며칠은 둘)."""
    out = []
    for r in JOSEON:
        if r.boundary and r.sillok_last and _key(r.boundary) <= _key(d) <= _key(r.sillok_last):
            out.append(_label(r, d))
    return out or ([x] if (x := from_lunar(d)) else [])
