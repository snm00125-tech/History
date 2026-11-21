"""날짜 변환. 모든 기록은 JDN(정수)에 매단다."""
from __future__ import annotations

from dataclasses import dataclass

from . import ganji
from .calendar import SolarDate, jdn_to_solar, solar_to_jdn
from .lunar import LunarDate, jdn_to_lunar, lunar_to_jdn
from .regnal import RegnalYear, from_lunar, to_lunar_year


def regnal_to_jdn(king: str, year: int, month: int, day: int, leap: bool = False) -> int:
    """왕력 + 음력 월일 → JDN. 예: regnal_to_jdn('선조', 25, 4, 13)."""
    return lunar_to_jdn(to_lunar_year(king, year), month, day, leap)


@dataclass(frozen=True, slots=True)
class DateInfo:
    jdn: int
    solar: SolarDate
    lunar: LunarDate
    regnal: RegnalYear | None
    year_ganji: str
    month_ganji: str | None
    day_ganji: str

    def as_dict(self) -> dict:
        return {
            "jdn": self.jdn,
            "solar": self.solar.iso(),
            "solar_calendar": "gregorian" if self.solar.gregorian else "julian",
            "lunar": {"year": self.lunar.year, "month": self.lunar.month,
                      "day": self.lunar.day, "leap": self.lunar.leap},
            "regnal": None if self.regnal is None else {
                "king": self.regnal.king, "year": self.regnal.year,
                "ambiguous": self.regnal.ambiguous},
            "ganji": {"year": self.year_ganji, "month": self.month_ganji, "day": self.day_ganji},
        }


def describe(jdn: int) -> DateInfo:
    lu = jdn_to_lunar(jdn)
    mi = ganji.month_index(lu.year, lu.month, lu.leap)
    return DateInfo(
        jdn=jdn,
        solar=jdn_to_solar(jdn),
        lunar=lu,
        regnal=from_lunar(lu),
        year_ganji=ganji.name(ganji.year_index(lu.year)),
        month_ganji=None if mi is None else ganji.name(mi),
        day_ganji=ganji.name(ganji.day_index(jdn)),
    )


__all__ = ["describe", "regnal_to_jdn", "lunar_to_jdn", "jdn_to_lunar",
           "solar_to_jdn", "jdn_to_solar", "DateInfo"]
