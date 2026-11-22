"""한국사료총서 원문(공공데이터포털 15053632, 국사편찬위원회 한국사데이터베이스) → 작업 DB.

    python3 -m sillok.load_sa data/raw/khdb_15053632/x data/work.sqlite

두 가지 방식으로 날짜를 얻는다.
1. 구조화된 날짜: level 요소의 dateOccured "1801-02-29"(L0/L1 붙기도 함). 일이 99·00이면 그달 단위.
   음력으로 읽는다(L1인데 그해에 그 윤달이 없으면 평달로 다시 시도).
2. 제목·본문 속 날짜(PARSED_BOOKS): 연 제목(간지) + 월 제목 + 본문의 「初二日」 같은 날 표시로 나눈다.
   간지 연도는 책마다 정한 시작 연도(anchor) 이후 첫 해로 푼다.

book 코드 = 파일 이름(sa_017 → sa017). 기사 ID = 원자료 요소 id(+ 날 나눔이면 _dNN).
책 이름은 book 표에 넣는다(내보내기가 읽는다). 링크: db.history.go.kr/id/<요소 id>.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from hdate import ganji
from .load import SCHEMA, _date_fields, _precision
from .parse import _article_text, _join_surrogates

BOOK_SCHEMA = """
CREATE TABLE IF NOT EXISTS book (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL
);
"""
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:L([01]))?$")

# 제목·본문 날짜로 나누는 책: 파일 → (책 이름, 첫 해 anchor)
PARSED_BOOKS = {
    "sa_017": ("쇄미록(瑣尾錄) 오희문", 1591),
}

_NUM = {"初": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        "正": 1, "廿": 20, "卄": 20}


def cn_num(s: str) -> int | None:
    """초일·十五·二十三·廿三 → 숫자."""
    s = s.replace("初", "")
    if not s:
        return None
    if s.startswith(("廿", "卄")):
        return 20 + (cn_num(s[1:]) or 0)
    if "十" in s:
        a, _, b = s.partition("十")
        tens = _NUM.get(a, 1) if a else 1
        return tens * 10 + (_NUM.get(b, 0) if b else 0)
    return _NUM.get(s) if len(s) == 1 else None


_MONTH_H = re.compile(r"(閏)?\s*(正|十[一二]?|[一二三四五六七八九])月")
_DAY = re.compile(r"(?:(?<=\s)|^)(?:(閏)?(正|十[一二]?|[一二三四五六七八九])月\s*)?(初[一二三四五六七八九十]|十[一二三四五六七八九]?|二十[一二三四五六七八九]?|廿[一二三四五六七八九]?|三十)日(?=\s|$)")
_GANJI_YEAR = re.compile(r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")


def _book_title(root) -> str:
    t = root.find("./front/biblioData/title/mainTitle")
    return (t.text or "").strip() if t is not None else ""


def _parse_root(path: Path):
    raw = path.read_bytes()
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return ET.fromstring(_join_surrogates(raw.decode("utf-8")))


def iter_structured(root):
    """dateOccured가 있는 요소 → (id, 제목, 날짜 ns, 본문, spans)."""
    for el in root.iter():
        if not el.tag.startswith("level"):
            continue
        d = el.find("./front/biblioData/date/dateOccured")
        if d is None or not (m := _DATE.match(d.get("date", ""))):
            continue
        y, mo, dd, lp = int(m[1]), int(m[2]), int(m[3]), m[4] == "1"
        t = el.find("./front/biblioData/title/mainTitle")
        text, spans = _article_text(el.find("text"))
        day = None if dd in (0, 99) else dd
        yield el.get("id"), (t.text or "").strip() if t is not None else "", \
            SimpleNamespace(year=y, month=mo, day=day, leap=lp, day_ganji=None), text, spans


def _year_from_ganji(gz: str, anchor: int) -> int:
    """anchor 이후(포함) 첫 번째 그 간지 해."""
    target = ganji.index_of(gz)
    for y in range(anchor, anchor + 60):
        if (y - 4) % 60 == target:
            return y
    raise ValueError(gz)


def iter_parsed(root, anchor: int):
    """연(간지) 제목 > 월 제목 > 본문 날 표시로 나눈다. 해 바뀜은 간지가 바뀔 때만."""
    year = None
    last_year = anchor - 1

    def walk(el, year, month, leap):
        nonlocal last_year
        t = el.find("./front/biblioData/title/mainTitle")
        title = (t.text or "").strip() if t is not None else ""
        if el.tag in ("level2", "level3") and (g := _GANJI_YEAR.search(title)):
            y = _year_from_ganji(g[1], last_year)
            year, last_year = y, y
        if (mh := _MONTH_H.search(title)) and len(title) <= 12:
            month, leap = cn_num(mh[2]), bool(mh[1])
        txt_el = el.find("text")
        if txt_el is not None and year and month:
            text, _ = _article_text(txt_el)
            yield from split_days(el.get("id"), title, text, year, month, leap)
        for ch in el:
            if ch.tag.startswith("level"):
                yield from walk(ch, year, month, leap)

    yield from walk(root, year, None, False)


def split_days(eid, title, text, year, month, leap):
    """본문을 날 표시(初二日 …)로 자른다. 날 번호가 앞으로만 가는 표시만 인정."""
    cuts = []
    last = 0
    start_month = month
    for m in _DAY.finditer(text):
        mo = cn_num(m[2]) if m[2] else None
        d = cn_num(m[3])
        if d is None or not 1 <= d <= 30:
            continue
        if mo and mo != month:
            if mo == month % 12 + 1:  # 다음 달로 넘어감
                month, leap, last = mo, bool(m[1]), 0
            else:
                continue
        if d <= last:
            continue
        cuts.append((m.start(), month, leap, d))
        last = d
    if not cuts:
        yield f"{eid}", title, SimpleNamespace(year=year, month=month, day=None, leap=leap, day_ganji=None), text.strip(), []
        return
    if cuts[0][0] > 0 and text[: cuts[0][0]].strip():
        yield f"{eid}_d00", title, SimpleNamespace(year=year, month=cuts[0][1], day=None, leap=cuts[0][2],
                                                  day_ganji=None), text[: cuts[0][0]].strip(), []
    for i, (pos, mo, lp, d) in enumerate(cuts):
        end = cuts[i + 1][0] if i + 1 < len(cuts) else len(text)
        body = text[pos:end].strip()
        head = body[:24].split()[0] if body.split() else ""
        yield f"{eid}_d{d:02d}" + ("" if mo == start_month else f"m{mo:02d}"), f"{title} {head}".strip(), \
            SimpleNamespace(year=year, month=mo, day=d, leap=lp, day_ganji=None), body, []


_DATEISH = re.compile(r"^[\[\]\s,()0-9甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥正一二三四五六七八九十初廿卄閏年月日大小晦朔·]*$")


def nice_title(title: str, text: str, n: int = 32) -> str:
    """제목이 날짜뿐이면 본문 첫머리를 붙인다."""
    if title and not _DATEISH.match(title):
        return title
    body = re.sub(r"\s+", " ", text).strip()
    t0 = re.sub(r"\s+", " ", title).strip()
    if t0 and body.startswith(t0):
        body = body[len(t0):].lstrip(" ,.、")
    body = _DAY.sub("", body, count=1).strip() if _DAY.match(body) else body
    snip = body[:n] + ("…" if len(body) > n else "")
    return f"{title} · {snip}" if title else snip


def load_sa(src: str, db: str) -> dict:
    con = sqlite3.connect(db)
    con.executescript(SCHEMA + BOOK_SCHEMA)
    stats = {}
    with con:
        old = [c for (c,) in con.execute("SELECT code FROM book WHERE source='sa'")]
        for code in old:
            for t in ("span", "ref_title_ko", "subject", "article_group"):
                con.execute(f"DELETE FROM {t} WHERE article_id IN (SELECT id FROM article WHERE book=?)", (code,))
            con.execute("DELETE FROM article WHERE book=?", (code,))
        con.execute("DELETE FROM book WHERE source='sa'")
        for f in sorted(Path(src).glob("sa_*.xml")):
            stem = f.stem
            root = _parse_root(f)
            if stem in PARSED_BOOKS:
                name, anchor = PARSED_BOOKS[stem]
                items = list(iter_parsed(root, anchor))
            else:
                items = list(iter_structured(root))
                name = _book_title(root)
            if not items:
                continue
            code = stem.replace("_", "")
            rows, titles, seen = [], [], set()
            for aid, title, a, text, _sp in items:
                if aid in seen or not text or (aid.endswith("_d00") and len(text.strip()) < 15):
                    continue
                seen.add(aid)
                j, jt, st, dl = _date_fields(a)
                if st == "invalid_date" and a.leap:  # 그해에 없는 윤달 → 평달로
                    a.leap = False
                    j, jt, st, dl = _date_fields(a)
                rows.append((aid, code, a.year, a.month, int(a.leap), a.day, None, j, jt, st, dl,
                             int(st == "invalid_date"), *_precision(a, code, j), text, "[]", "[]", f.name, None))
                titles.append((aid, nice_title(title, text)))
            con.executemany("INSERT INTO article VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.executemany("INSERT INTO ref_title_ko VALUES (?,?)", titles)
            con.execute("INSERT INTO book VALUES (?,?,?)", (code, name, "sa"))
            stats[code] = len(rows)
    return {"books": len(stats), "articles": sum(stats.values()), "per_book": stats}


if __name__ == "__main__":
    t = time.perf_counter()
    r = load_sa(sys.argv[1], sys.argv[2])
    print({k: v for k, v in r.items() if k != "per_book"}, f"{time.perf_counter() - t:.1f}s")
    for k, v in r["per_book"].items():
        print(" ", k, v)
