"""간지(干支). 인덱스 0 = 甲子."""
from __future__ import annotations

STEMS_HAN = "甲乙丙丁戊己庚辛壬癸"
STEMS_KO = "갑을병정무기경신임계"
BRANCHES_HAN = "子丑寅卯辰巳午未申酉戌亥"
BRANCHES_KO = "자축인묘진사오미신유술해"


def name(idx: int, hanja: bool = False) -> str:
    s, b = (STEMS_HAN, BRANCHES_HAN) if hanja else (STEMS_KO, BRANCHES_KO)
    return s[idx % 10] + b[idx % 12]


def index_of(text: str) -> int:
    """'임진' 또는 '壬辰' → 인덱스."""
    for s, b in ((STEMS_KO, BRANCHES_KO), (STEMS_HAN, BRANCHES_HAN)):
        if len(text) == 2 and text[0] in s and text[1] in b:
            si, bi = s.index(text[0]), b.index(text[1])
            for k in range(60):
                if k % 10 == si and k % 12 == bi:
                    return k
            raise ValueError(f"성립하지 않는 간지: {text}")
    raise ValueError(f"간지 아님: {text}")


def day_index(jdn: int) -> int:
    # JDN 2451545 (2000-01-01) = 戊午(54)
    return (jdn - 11) % 60


def year_index(lunar_year: int) -> int:
    return (lunar_year - 4) % 60  # 서기 4년 = 甲子


def month_index(lunar_year: int, month: int, leap: bool = False) -> int | None:
    """월건. 윤달은 고유 월건이 없으므로 None."""
    if leap:
        return None
    stem = (lunar_year - 4) % 10
    return ((stem % 5) * 12 + 2 + (month - 1)) % 60
