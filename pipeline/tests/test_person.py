"""인물: 초성 나누기, 조각 번호, 적재 결과."""
import sqlite3
from pathlib import Path

import pytest

from sillok.export_person import choseong, shard_of

DB = Path(__file__).parents[1] / "data" / "work.sqlite"


def test_choseong_and_shard():
    assert [choseong(x) for x in ("이순신", "김성일", "까치", "鄭撥", "")] == ["ㅇ", "ㄱ", "ㄲ", "etc", "etc"]
    assert shard_of("M_0004641") == 9 and shard_of("M_0000001") == 0


@pytest.mark.skipif(not DB.exists(), reason="작업 DB 없음")
def test_person_links():
    con = sqlite3.connect(DB)
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='article_person'").fetchone():
        pytest.skip("인물 미적재")
    # 정발(鄭撥)은 1592년 4월 13일 임진왜란 첫 기사에 나온다
    assert con.execute("SELECT 1 FROM article_person WHERE article_id='wna_12504013_001' AND person_id='M_0000882'").fetchone()
    assert con.execute("SELECT name_ko, born, died FROM person WHERE id='M_0004641'").fetchone() == ("이순신", 1545, 1598)
