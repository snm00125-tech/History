"""승정원일기(공공데이터 15064218) → 작업 DB. book = 'sjw'.

    python3 -m sillok.load_sjw data/raw/sjw_15064218/x data/work.sqlite

- 파일 2nd_<왕><연>.sjw.y.xml. level2 연 > level3 월 > level4 일(음력 날짜·일진·날씨) > level5 기사.
- 기사에는 제목이 없다('제목없음') → 본문 첫머리로 제목을 만든다(한문). 국편 국문 제목이 없음.
- 좌목(그날 승지 출근부)은 싣지 않는다.
- 날짜는 실록과 같은 규칙(_date_fields: 일진 우선, ±2일).
- 인조 1년(1623)~순종 4년(1910). 약 270만 건.
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
from .load_sa import BOOK_SCHEMA
from .parse import _article_text, _join_surrogates

_DATE = re.compile(r"^(\d{4})-(\d\d)-(\d\d)L(\d)$")
_REG = re.compile(r"^(\S+) (\d+)")


def make_title(text: str, n: int = 30) -> str:
    s = re.sub(r"\s+", " ", text).strip().lstrip("○ ").strip()
    return s if len(s) <= n else s[:n] + "…"


def _parse(path: Path):
    raw = path.read_bytes()
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return ET.fromstring(_join_surrogates(raw.decode("utf-8")))


def iter_file(path: Path):
    root = _parse(path)
    for day in root.iter("level4"):
        dates = day.findall("./front/biblioData/date/dateOccured")
        dt = next((d.get("date") for d in dates if d.get("type") == "서기" and d.get("date")), None)
        gz = next(((d.text or "").strip() for d in dates if d.get("type") == "간지"), None) or None
        reg = next(((d.text or "").strip() for d in dates if d.get("type") == "재위연도"), None)
        m = _DATE.match(dt or "")
        y = mo = dd = None
        leap = False
        if m:
            y, mo, dd, leap = int(m[1]), int(m[2]), int(m[3]), m[4] == "1"
            mo = None if mo in (0, 99) else mo
            dd = None if (mo is None or dd in (0, 99)) else dd
        rm = _REG.match(reg or "")
        regnal = f"{rm[1]} {int(rm[2])}" if rm else None
        a = SimpleNamespace(year=y, month=mo, day=dd, leap=leap, day_ganji=gz)
        for art in day.findall("level5"):
            if art.get("type") != "기사":
                continue
            txt = art.find("text")
            if txt is None:
                continue
            text, spans = _article_text(txt)
            if not text.strip():
                continue
            yield art.get("id"), a, text, spans, regnal


_GZ_KO = re.compile(r"[갑을병정무기경신임계][자축인묘진사오미신유술해]")


def _best_date(a):
    """일진 표기가 '갑신[갑오]'처럼 고친 값을 함께 적은 경우: 후보 중 표 날짜에 가장 가까운 것."""
    cands = _GZ_KO.findall(a.day_ganji or "") or [None]
    best = None
    for gz in dict.fromkeys(cands):
        for leap in dict.fromkeys((a.leap, False)):
            b = SimpleNamespace(year=a.year, month=a.month, day=a.day, leap=leap, day_ganji=gz)
            try:
                j, jt, st, d = _date_fields(b)
            except ValueError:
                continue
            score = (st == "invalid_date", abs(d) if d is not None else 99)
            if best is None or score < best[0]:
                best = (score, (j, jt, st, d, _precision(b, "sjw", j)))
        if best and best[0] == (False, 0):
            break
    return best[1] if best else (None, None, "invalid_date", None, ("none", None, None))


def load_sjw(src: str, db: str) -> dict:
    con = sqlite3.connect(db)
    con.executescript(SCHEMA + BOOK_SCHEMA)
    n = 0
    t0 = time.perf_counter()
    with con:
        for t in ("span", "ref_title_ko", "subject", "article_group"):
            con.execute(f"DELETE FROM {t} WHERE article_id IN (SELECT id FROM article WHERE book='sjw')")
        con.execute("DELETE FROM article WHERE book='sjw'")
        con.execute("DELETE FROM book WHERE code='sjw'")
        con.execute("INSERT INTO book VALUES ('sjw', '승정원일기', 'sjw')")
        cache: dict = {}
        for f in sorted(Path(src).glob("*.sjw.y.xml")):
            rows, titles, spans = [], [], []
            for aid, a, text, sp, regnal in iter_file(f):
                key = (a.year, a.month, a.day, a.leap, a.day_ganji)
                if key not in cache:
                    cache[key] = _best_date(a)
                j, jt, st, d, prec = cache[key]
                review = int(st in ("ganji_adjusted", "ganji_conflict", "invalid_date"))
                rows.append((aid, "sjw", a.year, a.month, int(a.leap), a.day, a.day_ganji, j, jt, st, d, review,
                             *prec, text, "[]", "[]", f.name, regnal))
                titles.append((aid, make_title(text)))
                spans += [(aid, s.kind, s.start, s.end, s.ref) for s in sp if not s.kind.startswith("index")]
            con.executemany("INSERT INTO article (id,book,lunar_year,lunar_month,lunar_leap,lunar_day,day_ganji_src,"
                            "jdn,jdn_table,jdn_status,ganji_delta,needs_review,date_precision,jdn_start,jdn_end,text,"
                            "subjects,sources,file,regnal_src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.executemany("INSERT INTO ref_title_ko VALUES (?,?)", titles)
            con.executemany("INSERT INTO span VALUES (?,?,?,?,?)", spans)
            n += len(rows)
            print(f"  {f.name} {len(rows):,} (누적 {n:,}, {time.perf_counter() - t0:.0f}s)", flush=True)
    con.close()
    return {"articles": n}


if __name__ == "__main__":
    t = time.perf_counter()
    print(load_sjw(sys.argv[1], sys.argv[2]), f"{time.perf_counter() - t:.1f}s")
