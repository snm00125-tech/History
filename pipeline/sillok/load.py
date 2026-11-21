"""실록 기사를 SQLite 작업 DB에 넣는다.

사용: python3 -m sillok.load <원문XML 디렉터리> <db 경로> [실록ID ...]
날짜: 기사 일진 우선. 음력 표로 구한 날짜(jdn_table)에서 ±MAX_ADJUST일 안에 일진이 맞는 날을 jdn으로 삼고
jdn_status='ganji_adjusted'(검수 대상)로 표시한다. 차이가 그보다 크면 역법 차이가 아니라 일진 오기
(子/午 혼동 등)로 보고 표 날짜를 유지하며 'ganji_conflict'(검수 대상)로 둔다.
국편 국문 제목은 ref_title_ko 표(검수 참고용)에만 넣는다. 내보내기에서 절대 읽지 않는다.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time

from hdate import ganji, lunar_to_jdn

from .category import groups_of, split_subject
from .parse import iter_files, parse_file

SCHEMA = """
CREATE TABLE IF NOT EXISTS article (
  id TEXT PRIMARY KEY,          -- wna_12504013_001
  book TEXT NOT NULL,           -- wna=선조실록, wnb=선조수정실록
  lunar_year INTEGER, lunar_month INTEGER, lunar_leap INTEGER NOT NULL DEFAULT 0, lunar_day INTEGER,
  day_ganji_src TEXT,           -- 기사 머리 일진(원자료)
  jdn INTEGER,                  -- 확정 JDN (일진 우선)
  jdn_table INTEGER,            -- 음력 표(hdate)로만 계산한 JDN
  jdn_status TEXT NOT NULL,     -- ok | ganji_adjusted | ganji_conflict | no_ganji | no_day | no_date | invalid_date
  ganji_delta INTEGER,          -- 일진 기준 차이(일). adjusted면 jdn - jdn_table
  needs_review INTEGER NOT NULL DEFAULT 0,
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
-- 분류: 국편 subjectClass 원본(subject)과 자체 상위 묶음(article_group)
CREATE TABLE IF NOT EXISTS subject (
  article_id TEXT NOT NULL REFERENCES article(id), raw TEXT NOT NULL, major TEXT NOT NULL, minor TEXT
);
CREATE INDEX IF NOT EXISTS subject_article ON subject(article_id);
CREATE TABLE IF NOT EXISTS article_group (
  article_id TEXT NOT NULL REFERENCES article(id), grp TEXT NOT NULL, rank INTEGER NOT NULL,
  PRIMARY KEY (article_id, grp)
);
CREATE INDEX IF NOT EXISTS article_group_grp ON article_group(grp);
-- 국사편찬위원회 국문 기사 제목(타 기관 번역 산물). 검수 때 대조용으로만 쓴다. 화면·내보내기 금지.
CREATE TABLE IF NOT EXISTS ref_title_ko (
  article_id TEXT PRIMARY KEY REFERENCES article(id), title TEXT NOT NULL
);
"""


MAX_ADJUST = 2  # 역법 차이(달 대소·초하루 차이)로 볼 최대 일수


def _date_fields(a):
    """→ (jdn, jdn_table, status, delta)"""
    if a.year is None:
        return None, None, "no_date", None
    if a.day is None:
        return None, None, "no_day", None
    try:
        jt = lunar_to_jdn(a.year, a.month, a.day, a.leap)
    except ValueError:
        jt = None
    if a.day_ganji is None:
        return jt, jt, ("no_ganji" if jt is not None else "invalid_date"), None
    if jt is None and not 1 <= a.day <= 30:
        return None, None, "invalid_date", None
    if jt is None:
        # 표에 없는 날(예: 29일까지인 달의 30일): 그 달 1일 기준으로 일진을 맞춘다
        try:
            base = lunar_to_jdn(a.year, a.month, 1, a.leap) + a.day - 1
        except ValueError:
            return None, None, "invalid_date", None
    else:
        base = jt
    delta = (ganji.index_of(a.day_ganji) - ganji.day_index(base) + 30) % 60 - 30
    if abs(delta) > MAX_ADJUST:
        return jt, jt, ("ganji_conflict" if jt is not None else "invalid_date"), delta
    j = base + delta
    status = "ok" if (jt is not None and delta == 0) else "ganji_adjusted"
    return j, jt, status, (j - jt) if jt is not None else None


def load(src_dir: str, db_path: str, books=None) -> dict:
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    n = 0
    with con:
        for f in iter_files(src_dir, books):
            book = f.name.split("_")[1]
            for t in ("span", "ref_title_ko", "subject", "article_group"):
                con.execute(f"DELETE FROM {t} WHERE article_id IN (SELECT id FROM article WHERE file=?)", (f.name,))
            con.execute("DELETE FROM article WHERE file=?", (f.name,))
            rows, spans, titles, subs, grps = [], [], [], [], []
            for a in parse_file(f):
                j, jt, st, d = _date_fields(a)
                review = int(st in ("ganji_adjusted", "ganji_conflict", "invalid_date"))
                rows.append((a.id, book, a.year, a.month, int(a.leap), a.day, a.day_ganji, j, jt, st, d, review,
                             a.text, json.dumps(a.subjects, ensure_ascii=False),
                             json.dumps(a.sources, ensure_ascii=False), f.name))
                spans += [(a.id, s.kind, s.start, s.end, s.ref) for s in a.spans]
                subs += [(a.id, x, *split_subject(x)) for x in a.subjects]
                grps += [(a.id, g, i) for i, g in enumerate(groups_of(a.subjects))]
                if a.title_ko_ref:
                    titles.append((a.id, a.title_ko_ref))
            con.executemany("INSERT INTO article VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.executemany("INSERT INTO span VALUES (?,?,?,?,?)", spans)
            con.executemany("INSERT INTO ref_title_ko VALUES (?,?)", titles)
            con.executemany("INSERT INTO subject VALUES (?,?,?,?)", subs)
            con.executemany("INSERT INTO article_group VALUES (?,?,?)", grps)
            n += len(rows)
    con.close()
    return {"articles": n}


if __name__ == "__main__":
    t = time.perf_counter()
    r = load(sys.argv[1], sys.argv[2], tuple(sys.argv[3:]) or None)
    print(r, f"{time.perf_counter() - t:.1f}s")
