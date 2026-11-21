"""실록 기사를 SQLite 작업 DB에 넣는다.

사용: python3 -m sillok.load <원문XML 디렉터리> <db 경로> [실록ID ...]
국문 기사 제목 등 번역 산물은 넣지 않는다 (CLAUDE.md 규칙 3).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time

from hdate import ganji, lunar_to_jdn

from .parse import iter_files, parse_file

SCHEMA = """
CREATE TABLE IF NOT EXISTS article (
  id TEXT PRIMARY KEY,          -- wna_12504013_001
  book TEXT NOT NULL,           -- wna=선조실록, wnb=선조수정실록
  lunar_year INTEGER, lunar_month INTEGER, lunar_leap INTEGER NOT NULL DEFAULT 0, lunar_day INTEGER,
  day_ganji_src TEXT,           -- 기사 머리 일진(원자료)
  jdn INTEGER,                  -- 음력 표(hdate)로 계산한 JDN
  jdn_status TEXT NOT NULL,     -- ok | ganji_mismatch | no_ganji | no_day | no_date | invalid_date
  ganji_delta INTEGER,          -- (기사 일진 - 계산 일진), -30..29
  text TEXT NOT NULL,           -- 원문(한문)
  subjects TEXT NOT NULL,       -- JSON 배열 (분류)
  sources TEXT NOT NULL,        -- JSON 배열 [판본, 쪽]
  file TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS article_jdn ON article(jdn);
CREATE INDEX IF NOT EXISTS article_lunar ON article(book, lunar_year, lunar_month, lunar_leap);
CREATE TABLE IF NOT EXISTS span (
  article_id TEXT NOT NULL REFERENCES article(id),
  kind TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL, ref TEXT
);
CREATE INDEX IF NOT EXISTS span_article ON span(article_id);
"""


def _date_fields(a):
    if a.year is None:
        return None, "no_date", None
    if a.day is None:
        return None, "no_day", None
    try:
        j = lunar_to_jdn(a.year, a.month, a.day, a.leap)
    except ValueError:
        return None, "invalid_date", None
    if a.day_ganji is None:
        return j, "no_ganji", None
    delta = (ganji.index_of(a.day_ganji) - ganji.day_index(j) + 30) % 60 - 30
    return j, ("ok" if delta == 0 else "ganji_mismatch"), delta


def load(src_dir: str, db_path: str, books=None) -> dict:
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    n = 0
    with con:
        for f in iter_files(src_dir, books):
            book = f.name.split("_")[1]
            con.execute("DELETE FROM span WHERE article_id IN (SELECT id FROM article WHERE file=?)", (f.name,))
            con.execute("DELETE FROM article WHERE file=?", (f.name,))
            rows, spans = [], []
            for a in parse_file(f):
                j, st, d = _date_fields(a)
                rows.append((a.id, book, a.year, a.month, int(a.leap), a.day, a.day_ganji, j, st, d,
                             a.text, json.dumps(a.subjects, ensure_ascii=False),
                             json.dumps(a.sources, ensure_ascii=False), f.name))
                spans += [(a.id, s.kind, s.start, s.end, s.ref) for s in a.spans]
            con.executemany("INSERT INTO article VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.executemany("INSERT INTO span VALUES (?,?,?,?,?)", spans)
            n += len(rows)
    con.close()
    return {"articles": n}


if __name__ == "__main__":
    t = time.perf_counter()
    r = load(sys.argv[1], sys.argv[2], tuple(sys.argv[3:]) or None)
    print(r, f"{time.perf_counter() - t:.1f}s")
