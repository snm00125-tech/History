"""비변사등록 원문(공공데이터포털 15053636, 국사편찬위원회 한국사데이터베이스) → 작업 DB의 article 표.

    python3 -m sillok.load_bb data/raw/khdb_15053636/x data/work.sqlite

- 기사 단위 = level4 (id 예: bb_001_002_01_0010). 제목(mainTitle)은 국편이 붙인 국한문 제목 → ref_title_ko.
- 날짜 = level4 dateOccured "1617-01-03L0" (음력). 일이 00이면 그달 단위(month 정밀도).
- 일진이 없어 대조 없이 음력 표로 정한다(jdn_status = no_ganji).
- book = "bb". 원문 링크는 db.history.go.kr/id/<ID>.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from .load import SCHEMA, _date_fields, _precision
from .parse import _article_text, _join_surrogates

BOOK = "bb"
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})L([01])$")


def parse_bb(path: Path):
    raw = path.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = ET.fromstring(_join_surrogates(raw.decode("utf-8")))
    for el in root.iter("level4"):
        title_el = el.find("./front/biblioData/title/mainTitle")
        title = (title_el.text or "").strip() if title_el is not None else ""
        d = el.find("./front/biblioData/date/dateOccured")
        y = m = day = None
        leap = False
        if d is not None and (mm := _DATE.match(d.get("date", ""))):
            y, m, day, leap = int(mm[1]), int(mm[2]), int(mm[3]) or None, mm[4] == "1"
        text, spans = _article_text(el.find("text"))
        yield el.get("id"), title, SimpleNamespace(year=y, month=m, day=day, leap=leap, day_ganji=None), text, spans


def load_bb(src: str, db: str) -> dict:
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    files = sorted(Path(src).rglob("bb_*.xml"))
    n = 0
    with con:
        for t in ("span", "ref_title_ko", "subject", "article_group"):
            con.execute(f"DELETE FROM {t} WHERE article_id IN (SELECT id FROM article WHERE book=?)", (BOOK,))
        con.execute("DELETE FROM article WHERE book=?", (BOOK,))
        for f in files:
            rows, spans, titles = [], [], []
            for aid, title, a, text, sp in parse_bb(f):
                if a.year is None:
                    j, jt, st, dl = None, None, "no_date", None
                else:
                    j, jt, st, dl = _date_fields(a)
                review = int(st == "invalid_date")
                rows.append((aid, BOOK, a.year, a.month, int(a.leap), a.day, None, j, jt, st, dl, review,
                             *_precision(a, BOOK, j), text, "[]", "[]", f.name, None))
                spans += [(aid, s.kind, s.start, s.end, s.ref) for s in sp]
                if title:
                    titles.append((aid, title))
            con.executemany("INSERT INTO article (id,book,lunar_year,lunar_month,lunar_leap,lunar_day,day_ganji_src,jdn,jdn_table,jdn_status,ganji_delta,needs_review,date_precision,jdn_start,jdn_end,text,subjects,sources,file,regnal_src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.executemany("INSERT INTO span VALUES (?,?,?,?,?)", spans)
            con.executemany("INSERT INTO ref_title_ko VALUES (?,?)", titles)
            n += len(rows)
    return {"files": len(files), "articles": n}


if __name__ == "__main__":
    t = time.perf_counter()
    print(load_bb(sys.argv[1], sys.argv[2]), f"{time.perf_counter() - t:.1f}s")
