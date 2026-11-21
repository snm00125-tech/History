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
    assert con.execute("SELECT jdn FROM article WHERE id='wzz_10104013_001'").fetchone()[0] == 2302669


@pytest.mark.skipif(not (RAW / "2nd_wna_125.xml").exists(), reason="원자료 없음")
def test_real_seonjo_25():
    t = time.perf_counter()
    arts = list(parse_file(RAW / "2nd_wna_125.xml"))
    assert time.perf_counter() - t < 1.0
    a = next(x for x in arts if x.id == "wna_12504013_001")
    assert a.day_ganji == "壬寅" and a.text.startswith("○十三日壬寅,倭寇至。")
