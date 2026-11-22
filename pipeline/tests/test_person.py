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


def test_match_terms_skips_person_names():
    from sillok.export import match_terms
    terms = [(0, "정언"), (1, "도승지"), (2, "승지"), (3, "대사헌")]
    ts = sorted(terms, key=lambda x: -len(x[1]))
    assert match_terms("도승지 이항복과 대사헌 김찬이 아뢰다", ts, []) == [1, 3]  # 승지는 도승지 안이라 따로 안 셈
    assert match_terms("정언신을 정언으로 삼다", ts, ["정언신"]) == [0]
    assert match_terms("정언신이 아뢰다", ts, ["정언신"]) == []
