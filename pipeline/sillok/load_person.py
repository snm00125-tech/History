"""실록 인물 정보(공공데이터포털 15053645, 국사편찬위원회 실록 부가정보) → 작업 DB.

    python3 -m sillok.load_person data/raw/person_15053645/x data/work.sqlite

표:
  person(id, name_ko, name_hj, ja, ho, siho, bongwan, born, died, kind)   — 인물 CSV
  person_office(person_id, lunar_year, lunar_month, lunar_day, leap, jdn, office, status, article_id)  — 관직 CSV
  article_person(article_id, person_id, n)  — 실록 원문 인명 색인(span ref M_…)에서. n = 그 기사에서 나온 횟수
관직 CSV의 기사 ID는 k로 시작(kma_…) → 실록 원문 ID는 w로 시작(wma_…)으로 바꾼다.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
import time
from pathlib import Path

from hdate import lunar_to_jdn

SCHEMA = """
DROP TABLE IF EXISTS person;
DROP TABLE IF EXISTS person_office;
DROP TABLE IF EXISTS article_person;
CREATE TABLE person (
  id TEXT PRIMARY KEY, name_ko TEXT, name_hj TEXT, ja TEXT, ho TEXT, siho TEXT, bongwan TEXT,
  born INTEGER, died INTEGER, kind TEXT
);
CREATE TABLE person_office (
  person_id TEXT NOT NULL, lunar_year INTEGER, lunar_month INTEGER, lunar_day INTEGER, leap INTEGER,
  jdn INTEGER, office TEXT, status TEXT, article_id TEXT
);
CREATE TABLE article_person (article_id TEXT NOT NULL, person_id TEXT NOT NULL, n INTEGER NOT NULL);
CREATE INDEX article_person_a ON article_person(article_id);
CREATE INDEX article_person_p ON article_person(person_id);
CREATE INDEX person_office_p ON person_office(person_id);
"""


def _int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _find(src: Path, suffix: str) -> Path:
    fs = [f for f in src.glob("*.csv") if f.name.endswith(suffix)]
    if len(fs) != 1:
        raise SystemExit(f"CSV를 찾지 못함: *{suffix}")
    return fs[0]


def load_person(src: str, db: str) -> dict:
    srcp = Path(src)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    with con:
        rows = []
        with open(_find(srcp, "#Uc778#Ubb3c.csv"), encoding="utf-8-sig", newline="") as f:  # 인물
            for r in csv.DictReader(f):
                rows.append((r["인물아이디"], r["한글_명"] or r["한글_이름"], r["한자_명"] or r["한자_이름"],
                             r["한글_자"], r["한글_호"], r["한글_시호"], r["한글_본관"],
                             _int(r["생년"]), _int(r["몰년"]), r["관직"]))
        con.executemany("INSERT OR REPLACE INTO person VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

        offs = []
        with open(_find(srcp, "#Uad00#Uc9c1.csv"), encoding="utf-8-sig", newline="") as f:  # 관직
            for r in csv.DictReader(f):
                y, m, d, lp = _int(r["년"]), _int(r["월"]), _int(r["일"]), r["윤달여부"] == "1"
                try:
                    j = lunar_to_jdn(y, m, d, lp) if y and m and d else None
                except ValueError:
                    j = None
                aid = r["파라아이디"]
                if aid.startswith("k"):
                    aid = "w" + aid[1:]
                offs.append((r["인물아이디"], y, m, d, int(lp), j, r["관력"], r["형태"], aid))
        con.executemany("INSERT INTO person_office VALUES (?,?,?,?,?,?,?,?,?)", offs)

        con.execute("""INSERT INTO article_person
                       SELECT article_id, ref, COUNT(*) FROM span
                       WHERE kind='index:이름' AND ref LIKE 'M\\_%' ESCAPE '\\'
                       GROUP BY article_id, ref""")
    n_ap = con.execute("SELECT COUNT(*) FROM article_person").fetchone()[0]
    return {"persons": len(rows), "offices": len(offs), "article_person": n_ap}


if __name__ == "__main__":
    t = time.perf_counter()
    print(load_person(sys.argv[1], sys.argv[2]), f"{time.perf_counter() - t:.1f}s")
