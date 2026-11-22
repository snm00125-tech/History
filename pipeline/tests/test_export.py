import json
import sqlite3
import time
from pathlib import Path

from sillok.export import export
from sillok.load import load

FIX = Path(__file__).parent / "fixtures"


def test_export_fixture(tmp_path):
    db = tmp_path / "t.sqlite"
    load(str(FIX), str(db))
    con = sqlite3.connect(db)
    con.executescript("""
      CREATE TABLE IF NOT EXISTS summary(article_id TEXT PRIMARY KEY, title TEXT, sentences TEXT,
        commentary TEXT, author TEXT, review_status TEXT, source_file TEXT);""")
    con.execute("INSERT INTO summary VALUES ('wzz_10104013_001', '왜군 침입', ?, NULL, 't', 'draft', 'x')",
                (json.dumps([{"text": "왜군이 왔다.", "evidence": [{"start": 7, "end": 10, "quote": "倭寇至"}]}]),))
    con.commit()
    out = tmp_path / "web"
    t = time.perf_counter()
    r = export(con, out, 1592, 1592)
    assert time.perf_counter() - t < 2
    assert r == {"months": 1, "articles": 2, "summarized": 1, "skipped": 1}  # 없는 윤4월은 빠짐

    raw = (out / "months" / "1592-04.json").read_text(encoding="utf-8")
    assert "국문 제목은 저장하지 않는다" not in raw  # 국편 번역 제목은 내보내지 않는다
    m = json.loads(raw)
    assert m["solar_start"] == "1592-05-11" and m["regnal"][0]["king"] == "선조"
    day = m["days"][0]
    assert day["date"]["jdn"] == 2302669 and day["date"]["ganji"]["day"] == "임인"
    a = day["articles"][0]
    assert a["url"].endswith("/wzz_10104013_001")
    assert a["summary"]["sentences"][0]["evidence"] == [[7, 10]]
    assert [x["id"] for x in m["month_articles"]] == ["wzz_101040??_001"]  # 일 미상 → 달 단위

    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert idx["n_articles"] == 2 and idx["months"][0]["days"][0]["titles"] == ["왜군 침입"]
