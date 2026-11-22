"""1000년 이전 추정 음력(hdate.ancient)과 국편 편년 사서 날짜 규칙(sillok.load_kh)."""
import collections
import time

from hdate import ancient, describe, ganji, lunar
from sillok.load_kh import astro_year, date_fields


def test_ancient_matches_kasi_mostly():
    """KASI 표가 있는 1001~1399년에서 달 첫날이 90% 가까이 같아야 한다(추정 역법의 정확도 기준)."""
    t = time.perf_counter()
    d = collections.Counter()
    for (y, m, lp), i in lunar._INDEX.items():
        if 1001 <= y < 1400:
            try:
                d[ancient.lunar_to_jdn(y, m, 1, lp) - lunar._MONTH_START[i]] += 1
            except ValueError:
                d["x"] += 1
    total = sum(d.values())
    assert d[0] / total > 0.88
    assert (d[0] + d[-1] + d[1]) / total > 0.93
    assert time.perf_counter() - t < 10


def test_bc_year_and_describe():
    assert astro_year(-57) == -56 and astro_year(918) == 918
    j = ancient.lunar_to_jdn(-56, 4, 15)
    d = describe(j)
    assert d.lunar_estimated and d.year_ganji == "갑자"  # 혁거세 즉위 기원전 57년 = 甲子
    assert ancient.jdn_to_lunar(j)[:3] == (-56, 4, 15)


def test_date_rules():
    # 원자료 양력이 1000년 이후 표와 크게 다르면 표 날짜를 쓰고 검수로 넘긴다
    jt = lunar.lunar_to_jdn(1348, 12, 5)
    f = date_fields(1348, 12, 5, False, solar=jt - 357)
    assert f["status"] == "solar_conflict" and f["jdn"] == jt and f["review"] == 1
    # 같으면 원자료 양력
    assert date_fields(1348, 12, 5, False, solar=jt)["status"] == "solar_src"
    # 1000년 이전 + 일진: ±2일 안에서 맞춘다, 추정 표시
    j0 = ancient.lunar_to_jdn(500, 3, 10)
    gz = ganji.name(ganji.day_index(j0 + 1), hanja=True)
    f = date_fields(500, 3, 10, False, gz=gz)
    assert f["jdn"] == j0 + 1 and f["status"] == "est_ganji_adjusted" and f["review"] == 0
    # 달 미상 → 그해 전체
    f = date_fields(1100, None, None, False)
    assert f["precision"] == "year" and f["start"] == lunar.lunar_to_jdn(1100, 1, 1)


def test_korean_king_name():
    from sillok.load_kh import _ACCESSION
    assert _ACCESSION.match("시조 혁거세가 즉위하다")[1] == "혁거세"
    assert _ACCESSION.match("법흥왕이 왕위에 오르다")[1] == "법흥왕"
    assert _ACCESSION.match("아달라이사금이 즉위하다")[1] == "아달라이사금"
