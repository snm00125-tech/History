"""요약 검수용 Markdown 생성. 국편 국문 제목은 싣지 않는다.

사용: python3 -m sillok.review <db> <출력.md> <연> <월> [윤달이면 1]
"""
from __future__ import annotations

import json
import sqlite3
import sys

from hdate import describe

from .category import GROUP_NAMES
from .parse import SILLOK_URL

BOOK = {"wna": "선조실록", "wnb": "선조수정실록"}


def render(db: str, y: int, m: int, leap: int = 0) -> str:
    con = sqlite3.connect(db)
    q = """SELECT a.id, a.book, a.lunar_day, a.jdn, a.jdn_status, a.text, s.title, s.sentences, s.commentary
           FROM article a LEFT JOIN summary s ON s.article_id = a.id
           WHERE a.lunar_year=? AND a.lunar_month=? AND a.lunar_leap=? ORDER BY a.book, a.id"""
    out = [f"# 요약 검수: {y}년 {'윤' if leap else ''}{m}월", "",
           "근거 구절은 원문에서 그대로 찾은 위치다. 해설은 원문 밖 설명이라 검수 전(미확인)이다.", ""]
    for aid, book, day, jdn, st, text, title, sents, com in con.execute(q, (y, m, leap)):
        grps = [GROUP_NAMES[g] for (g,) in con.execute(
            "SELECT grp FROM article_group WHERE article_id=? ORDER BY rank", (aid,))]
        if jdn is not None:
            d = describe(jdn)
            when = f"{d.regnal} {d.lunar.month}월 {day}일({d.day_ganji}) · 양력 {d.solar.iso()} · JDN {jdn}"
        else:
            when = f"{day or '?'}일 · 날짜 {st}"
        out += [f"## {BOOK.get(book, book)} [{aid}]({SILLOK_URL.format(id=aid)})", "",
                f"{when} · {' / '.join(grps)}" + ("" if st == "ok" else f" · ⚠ {st}"), ""]
        if not title:
            out += ["(요약 없음)", ""]
            continue
        out += [f"**{title}**", ""]
        for i, s in enumerate(json.loads(sents), 1):
            quotes = " · ".join(f"`{e['quote']}`@{e['start']}" for e in s["evidence"])
            out += [f"{i}. {s['text']}", f"   - 근거: {quotes}"]
        if com:
            out += [""] + [f"> 해설(미확인): {c['text']}" for c in json.loads(com)]
        out += ["", "<details><summary>원문</summary>", "", text.replace("\n", "  \n"), "", "</details>", ""]
    return "\n".join(out)


if __name__ == "__main__":
    db, path, y, m = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    leap = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    open(path, "w", encoding="utf-8").write(render(db, y, m, leap))
    print(path)
