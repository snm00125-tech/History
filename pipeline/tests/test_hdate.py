import time

import pytest

from hdate import describe, jdn_to_lunar, jdn_to_solar, lunar_to_jdn, regnal_to_jdn, solar_to_jdn
from hdate import ganji
from hdate.calendar import GREGORIAN_START_JDN, gregorian_to_jdn, julian_to_jdn
from hdate.lunar import END_JDN, FIRST_JDN, leap_month_of, month_length
from hdate.regnal import from_lunar, to_lunar_year


# --- 설계서 검증 예 ---
def test_seonjo_25_4_13():
    j = regnal_to_jdn("선조", 25, 4, 13)
    info = describe(j)
    assert info.solar.iso() == "1592-05-23" and info.solar.gregorian
    assert str(info.regnal) == "선조 25년"
    assert info.year_ganji == "임진"


# --- 양력 ---
def test_gregorian_switch():
    assert jdn_to_solar(GREGORIAN_START_JDN - 1).iso() == "1582-10-04"
    assert not jdn_to_solar(GREGORIAN_START_JDN - 1).gregorian
    assert jdn_to_solar(GREGORIAN_START_JDN).iso() == "1582-10-15"
    assert jdn_to_solar(GREGORIAN_START_JDN).gregorian
    with pytest.raises(ValueError):
        solar_to_jdn(1582, 10, 10)


def test_known_jdn():
    assert gregorian_to_jdn(2000, 1, 1) == 2451545
    assert julian_to_jdn(-4712, 1, 1) == 0
    assert solar_to_jdn(1392, 8, 5) == julian_to_jdn(1392, 8, 5)


def test_invalid_solar():
    with pytest.raises(ValueError):
        solar_to_jdn(1500, 2, 30)


# --- 음력 ---
@pytest.mark.parametrize("lunar,solar", [
    ((2024, 1, 1), "2024-02-10"),
    ((1900, 1, 1), "1900-01-31"),
    ((2000, 1, 1), "2000-02-05"),
])
def test_modern_new_year(lunar, solar):
    assert jdn_to_solar(lunar_to_jdn(*lunar)).iso() == solar


def test_roundtrip_all_days():
    """표 전 구간에서 JDN→음력→JDN 왕복이 일치해야 한다."""
    for j in range(FIRST_JDN, END_JDN):
        lu = jdn_to_lunar(j)
        assert lunar_to_jdn(lu.year, lu.month, lu.day, lu.leap) == j


def test_leap_month_and_bounds():
    y = 2023  # 2023년 윤2월
    assert leap_month_of(y) == 2
    assert lunar_to_jdn(y, 2, 1, True) == lunar_to_jdn(y, 2, month_length(y, 2)) + 1
    with pytest.raises(ValueError):
        lunar_to_jdn(y, 3, 1, True)
    with pytest.raises(ValueError):
        lunar_to_jdn(y, 1, 31)


# --- 간지 ---
def test_ganji():
    assert ganji.day_index(2451545) == ganji.index_of("무오")  # 2000-01-01
    assert ganji.name(ganji.year_index(1592)) == "임진"
    assert ganji.name(ganji.year_index(1592), hanja=True) == "壬辰"
    assert ganji.index_of("壬辰") == ganji.index_of("임진")
    with pytest.raises(ValueError):
        ganji.index_of("갑축")
    assert ganji.month_index(1592, 1) == ganji.index_of("임인")  # 壬년 정월 = 壬寅
    assert ganji.month_index(1592, 1, leap=True) is None


# --- 왕력 ---
def test_regnal():
    assert to_lunar_year("선조", 1) == 1568
    assert to_lunar_year("선조", 0) == 1567
    with pytest.raises(ValueError):
        to_lunar_year("인조", 0)  # 즉위년칭원
    for y in range(1592, 1599):
        r = from_lunar(jdn_to_lunar(lunar_to_jdn(y, 6, 1)))
        assert r.king == "선조" and r.year == y - 1567 and not r.ambiguous
    # 즉위일 미확정인 해는 ambiguous로 표시
    assert from_lunar(jdn_to_lunar(lunar_to_jdn(1608, 6, 1))).ambiguous


# --- 속도 ---
def test_speed():
    t = time.perf_counter()
    for j in range(2302000, 2302000 + 100_000):
        describe(j % (END_JDN - FIRST_JDN) + FIRST_JDN)
    assert time.perf_counter() - t < 2.0
