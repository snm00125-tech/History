"""연도 범위의 기사 수를 음력 월별로 집계한다 (실록 자체의 월 표기 기준).

사용: python3 -m sillok.report <db> <시작년> <끝년> [실록ID ...]
"""
from __future__ import annotations

import sqlite3
import sys

NAMES = {"wna": "선조실록", "wnb": "선조수정실록"}


def monthly(db: str, y0: int, y1: int, books: tuple[str, ...]):
    con = sqlite3.connect(db)
    q = f"""SELECT lunar_year, lunar_month, lunar_leap, book, COUNT(*)
            FROM article WHERE lunar_year BETWEEN ? AND ? AND book IN ({','.join('?'*len(books))})
            GROUP BY 1,2,3,4 ORDER BY 1,2,3"""
    out = {}
    for y, m, lp, b, c in con.execute(q, (y0, y1, *books)):
        out.setdefault((y, m, lp), {})[b] = c
    return out


if __name__ == "__main__":
    db, y0, y1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    books = tuple(sys.argv[4:]) or ("wna", "wnb")
    data = monthly(db, y0, y1, books)
    print("| 음력 연월 | " + " | ".join(NAMES.get(b, b) for b in books) + " |")
    print("|---|" + "---:|" * len(books))
    tot = {b: 0 for b in books}
    for (y, m, lp), c in data.items():
        print(f"| {y}년 {'윤' if lp else ''}{m}월 | " + " | ".join(str(c.get(b, 0)) for b in books) + " |")
        for b in books:
            tot[b] += c.get(b, 0)
    print("| **합계** | " + " | ".join(f"**{tot[b]}**" for b in books) + " |")
