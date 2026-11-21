import os
import sqlite3
import time
from pathlib import Path

import pytest

from sillok.load import load
from sillok.parse import NEWCHAR_MARK, parse_file

FIX = Path(__file__).parent / "fixtures" / "2nd_wzz_101.xml"
RAW = Path(__file__).parents[1] / "data" / "raw" / "sillok_15053647" / "x"


def test_parse_fixture():
    arts = list(parse_file(FIX))
    assert [a.id for a in arts] == ["wzz_10104013_001", "wzz_101040??_001", "wzz_10104101_001"]
    a = arts[0]
    assert (a.year, a.month, a.day, a.leap, a.day_ganji) == (1592, 4, 13, False, "壬寅")
    assert a.subjects == ["군사(軍事)"]
    assert a.sources == [("태백산사고본:某實錄 1책 1권", "1장 A면")]
    assert "국문" not in a.text  # 국문 제목은 본문에 섞이지 않는다
    assert a.text.startswith("○東萊府使宋象賢 象賢死之,【注】(嘗)〔賞〕李\U0002554F金" + NEWCHAR_MARK + " 李")
    assert a.text.endswith("李\U0002563C\n第二段")  # 대리쌍 참조 &#55381;&#56892; = U+2563C
    assert a.text.endswith("\n第二段")
    kinds = {(s.kind, a.text[s.start:s.end], s.ref) for s in a.spans}
    assert ("index:지명", "東萊", None) in kinds
    assert ("index:이름", "宋象賢", "M_1") in kinds
    assert ("원주", "【注】", None) in kinds
    assert ("교감주", "〔賞〕", None) in kinds
    assert ("newchar", NEWCHAR_MARK, "KC00001") in kinds
    assert a.url == "https://sillok.history.go.kr/id/wzz_10104013_001"
    b, c = arts[1], arts[2]
    assert b.day is None and b.day_ganji is None
    assert c.leap and c.day == 1


def test_load_fixture(tmp_path):
    db = tmp_path / "t.sqlite"
    load(str(FIX.parent), str(db))
    load(str(FIX.parent), str(db))  # 다시 넣어도 중복되지 않는다
    con = sqlite3.connect(db)
    rows = dict(con.execute("SELECT id, jdn_status FROM article").fetchall())
    assert rows == {"wzz_10104013_001": "ok", "wzz_101040??_001": "no_day",
                    "wzz_10104101_001": "invalid_date"}  # 1592년에는 윤4월이 없다
    # 국문 제목은 검수 참고 표에만 있고 article에는 없다
    assert con.execute("SELECT title FROM ref_title_ko").fetchall() == [("국문 제목은 저장하지 않는다",)]
    assert "국문" not in con.execute("SELECT group_concat(text) FROM article").fetchone()[0]
    assert con.execute("SELECT jdn FROM article WHERE id='wzz_10104013_001'").fetchone()[0] == 2302669
    prec = {r[0]: r[1:] for r in con.execute("SELECT id, date_precision, jdn_start, jdn_end FROM article")}
    assert prec["wzz_10104013_001"] == ("day", 2302669, 2302669)
    s0 = 2302669 - 12  # 1592년 4월 1일
    assert prec["wzz_101040??_001"] == ("month", s0, s0 + 29)  # 일 미상 → 그달 (4월은 30일)
    assert prec["wzz_10104101_001"] == ("none", None, None)    # 없는 윤4월


@pytest.mark.skipif(not (RAW / "2nd_wna_125.xml").exists(), reason="원자료 없음")
def test_real_seonjo_25():
    t = time.perf_counter()
    arts = list(parse_file(RAW / "2nd_wna_125.xml"))
    assert time.perf_counter() - t < 1.0
    a = next(x for x in arts if x.id == "wna_12504013_001")
    assert a.day_ganji == "壬寅" and a.text.startswith("○十三日壬寅,倭寇至。")


def test_ganji_first():
    from types import SimpleNamespace as N
    from sillok.load import _date_fields
    # 선조실록 1592년 9월 1일 朔戊午: 표로는 丁巳 → 하루 뒤로 보정, 검수 대상
    j, jt, st, d = _date_fields(N(year=1592, month=9, day=1, leap=False, day_ganji="戊午"))
    assert (j - jt, st, d) == (1, "ganji_adjusted", 1)
    # 표에 없는 날(1602년 8월 30일 己未)도 일진으로 잡는다
    j, jt, st, d = _date_fields(N(year=1602, month=8, day=30, leap=False, day_ganji="己未"))
    assert jt is None and st == "ganji_adjusted" and j is not None
    # 99일 같은 깨진 날짜는 보정하지 않는다
    assert _date_fields(N(year=1569, month=12, day=99, leap=False, day_ganji="甲子"))[2] == "invalid_date"
    # 子/午 같은 오기(30일 차이)는 옮기지 않고 충돌로 표시
    j, jt, st, d = _date_fields(N(year=1592, month=4, day=13, leap=False, day_ganji="壬申"))
    assert (j, jt, st, d) == (2302669, 2302669, "ganji_conflict", -30)


def test_month_precision_book():
    from types import SimpleNamespace as N
    from sillok.load import _precision
    a = N(year=1592, month=4, day=14, leap=False)
    assert _precision(a, "wnb", 2302670) == ("month", 2302657, 2302686)
    assert _precision(a, "wna", 2302670) == ("day", 2302670, 2302670)
