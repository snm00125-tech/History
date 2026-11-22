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

from hdate import ganji, lunar
from .load import SCHEMA, _date_fields, _precision
from .parse import _article_text, _join_surrogates

BOOK_SCHEMA = """
CREATE TABLE IF NOT EXISTS book (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL
);
"""
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:L([01]))?$")

# 제목·본문 날짜로 나누는 책: 파일 → (책 이름, 첫 해 anchor)
PARSED_BOOKS = {  # 파일 → (화면 이름, 첫 해 anchor. None이면 제목 속 확실한 연도에서 찾음)
    "sa_017": ("쇄미록(瑣尾錄) 오희문", 1591),
    "sa_074": ("계암일록(溪巖日錄) 김령 1", 1603),
    "sa_075": ("계암일록(溪巖日錄) 김령 2", 1627),
    "sa_076": ("묵재일기(默齋日記) 이문건 1", None),
    "sa_077": ("묵재일기(默齋日記) 이문건 2", None),
    "sa_079": ("향병일기·매원일기(鄕兵日記·梅園日記)", 1592),
    "sa_080": ("묵재일기·여온일기·과헌일기", None),
    "sa_089": ("노상추일기(盧尙樞日記) 1", None),
    "sa_090": ("노상추일기(盧尙樞日記) 2", None),
    "sa_091": ("노상추일기(盧尙樞日記) 3", None),
    "sa_092": ("노상추일기(盧尙樞日記) 4", None),
    "sa_126": ("노𥳂일기", None),
    "sa_057": ("봉서일기·봉남일기(鳳棲日記·鳳南日記)", None),
    "sa_062": ("향산일기(響山日記) 이만도", None),
    "sa_069": ("죽계일기(竹溪日記)", None),
    "sa_039": ("청우일록(靑又日錄)", None),
    "sa_060": ("일신(日新)", None),
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
    if s.startswith("卅"):
        return 30 + (cn_num(s[1:]) or 0)
    if "十" in s:
        a, _, b = s.partition("十")
        tens = _NUM.get(a, 1) if a else 1
        return tens * 10 + (_NUM.get(b, 0) if b else 0)
    return _NUM.get(s) if len(s) == 1 else None


def day_num(s: str, year: int, month: int | None, leap: bool) -> int | None:
    """날 표시 → 날 번호. 晦(그믐)는 그달 마지막 날."""
    if s != "晦":
        return cn_num(s)
    try:
        return lunar.month_length(year, month, leap)
    except Exception:
        return None


_MONTH_H = re.compile(r"(閏)?\s*(正|十[一二]?|[一二三四五六七八九])月")
_DAY = re.compile(r"(?:(?<=\s)|^)(?:(閏)?(正|十[一二]?|[一二三四五六七八九])月\s*)?(初[一二三四五六七八九十]|十[一二三四五六七八九]?|二十[一二三四五六七八九]?|[廿卄][一二三四五六七八九]?|三十|晦)日(?=[\s,.、。:;甲乙丙丁戊己庚辛壬癸]|$)")
# 初 없이 쓴 一日~九日: 줄 맨 앞일 때만 날 표시로 본다(본문 속 "一日"은 '하루'일 수 있다).
_DAY_BARE = re.compile(r"(?:(?<=\n)|^)[ \t]*(?:(閏)?(正|十[一二]?|[一二三四五六七八九])月\s*)?([一二三四五六七八九])日")


def _day_marks(text):
    ms = list(_DAY.finditer(text)) + list(_DAY_BARE.finditer(text))
    seen, out = set(), []
    for m in sorted(ms, key=lambda m: m.start(3)):
        if m.start(3) not in seen:
            seen.add(m.start(3)); out.append(m)
    return out


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
    for m in _day_marks(text):
        mo = cn_num(m[2]) if m[2] else None
        if mo and mo != month and mo != month % 12 + 1:
            continue
        d = day_num(m[3], year, mo or month, bool(m[1]) if mo else leap)
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


_HEAD_GZ = re.compile(r"日\s*([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")
YEAR_SHIFTS = (0, -1, 1, 60, -60, 120, -120)


def _gz_hits(group, shift):
    """(맞음, 대조 가능) — 머리 일진과 계산 일진."""
    ok = n = 0
    for _aid, _t, a, text, _sp in group:
        if not a.day or not (m := _HEAD_GZ.search(text[:16])):
            continue
        try:
            j = lunar.lunar_to_jdn(a.year + shift, a.month, a.day, a.leap)
            want = ganji.index_of(m[1])
        except Exception:  # 표 밖 날짜, 성립하지 않는 간지(원자료 오기)
            continue
        n += 1
        ok += ganji.day_index(j) == want
    return ok, n


def fix_years_by_ganji(items):
    """같은 해·같은 묶음(월 제목의 부모) 기사들의 머리 일진이 안 맞으면 ±1·±60년을 시험해 맞는 해로 옮긴다.
    (원자료 연도 주석 오류, 간지만 적힌 해를 60년 틀리게 짚은 경우)"""
    groups: dict = {}
    for it in items:
        key = (it[2].year, it[0].rsplit("_", 2)[0] if "_d" in it[0] else it[0].rsplit("_", 1)[0])
        groups.setdefault(key, []).append(it)
    shift_of = {}
    for key, g in groups.items():
        ok0, n = _gz_hits(g, 0)
        if n < 5 or ok0 >= 0.6 * n:
            continue
        best = max(YEAR_SHIFTS, key=lambda s: _gz_hits(g, s)[0])
        okb, _ = _gz_hits(g, best)
        if best and okb >= 0.8 * n:
            shift_of[key] = best
    out = []
    for it in items:
        key = (it[2].year, it[0].rsplit("_", 2)[0] if "_d" in it[0] else it[0].rsplit("_", 1)[0])
        if (s := shift_of.get(key)):
            a = it[2]
            it = (it[0], it[1], SimpleNamespace(**{**vars(a), "year": a.year + s}), it[3], it[4])
        out.append(it)
    FIXED.extend((k, v) for k, v in shift_of.items())
    return out


FIXED: list = []


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
                items = fix_years_by_ganji(list(iter_generic(root, anchor)))
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
            con.executemany("INSERT INTO article (id,book,lunar_year,lunar_month,lunar_leap,lunar_day,day_ganji_src,jdn,jdn_table,jdn_status,ganji_delta,needs_review,date_precision,jdn_start,jdn_end,text,subjects,sources,file,regnal_src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.executemany("INSERT INTO ref_title_ko VALUES (?,?)", titles)
            con.execute("INSERT INTO book VALUES (?,?,?)", (code, name, "sa"))
            stats[code] = len(rows)
    return {"books": len(stats), "articles": sum(stats.values()), "per_book": stats}


# ---------------- 일반 일기 해석기 (여러 날짜 표기) ----------------
_HNUM = {"〇": 0, "○": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KING_HJ = {"太祖": "태조", "太宗": "태종", "世宗": "세종", "世祖": "세조", "成宗": "성종", "中宗": "중종", "明宗": "명종",
            "宣祖": "선조", "仁祖": "인조", "孝宗": "효종", "顯宗": "현종", "肅宗": "숙종", "景宗": "경종", "英宗": "영조",
            "英祖": "영조", "正宗": "정조", "正祖": "정조", "純宗": "순조", "純祖": "순조", "憲宗": "헌종", "哲宗": "철종",
            "高宗": "고종"}
_ERA = {"嘉靖": 1522, "隆慶": 1567, "萬曆": 1573, "天啓": 1621, "崇禎": 1628, "順治": 1644, "康熙": 1662, "雍正": 1723,
        "乾隆": 1736, "嘉慶": 1796, "道光": 1821, "咸豐": 1851, "同治": 1862, "光緖": 1875, "光緒": 1875, "建陽": 1896,
        "光武": 1897, "隆熙": 1907}
_NUMS = "元一二三四五六七八九十百廿卅"
_WEST = re.compile(r"(1[3-9]\d\d)\s*年?|([一二〇○][一二三四五六七八九〇○零]{3})")
_REGNAL = re.compile(rf"({'|'.join(_KING_HJ)})\s*([{_NUMS}]+)\s*年")
_ERA_RE = re.compile(rf"({'|'.join(_ERA)})\s*([{_NUMS}]+)\s*年")
_MONTH_FULL = re.compile(r"(閏)?\s*(?:[孟仲季][春夏秋冬])?\s*(正|十[一二]?|[一二三四五六七八九])月")
_DAY_HEAD = re.compile(r"^\[?\s*(?:(閏)?(正|十[一二]?|[一二三四五六七八九])月\s*)?(初[一二三四五六七八九十]|十[一二三四五六七八九]?|二十[一二三四五六七八九]?|[廿卄][一二三四五六七八九]?|三十|晦|[一二三四五六七八九])日")


def _cn_year_num(s: str) -> int | None:
    return 1 if s == "元" else cn_num(s.replace("百", ""))  # 백 단위는 쓰이지 않는다


def explicit_year(title: str) -> int | None:
    """제목 속 확실한 연도: 서기(1866·一八六六) > 왕력(英宗三十九年) > 중국 연호(嘉靖十四年)."""
    if m := _WEST.search(title):
        if m[1]:
            return int(m[1])
        return int("".join(str(_HNUM[c]) for c in m[2]))
    if m := _REGNAL.search(title):
        n = _cn_year_num(m[2])
        if n:
            from hdate.regnal import to_lunar_year
            try:
                return to_lunar_year(_KING_HJ[m[1]], n)
            except Exception:
                return None
    if m := _ERA_RE.search(title):
        n = _cn_year_num(m[2])
        if n:
            return _ERA[m[1]] + n - 1
    return None


def first_explicit_year(root) -> int | None:
    for el in root.iter():
        if el.tag.startswith("level"):
            t = el.find("./front/biblioData/title/mainTitle")
            if t is not None and (y := explicit_year(t.text or "")):
                return y
    return None


def iter_generic(root, anchor: int | None):
    """연(서기·왕력·연호·간지) > 월 > 날(제목 또는 본문 표시)을 따라 내려가며 기사로 나눈다."""
    start = anchor or first_explicit_year(root)
    if not start:
        return
    state = {"last": start - 1}

    def walk(el, year, month, leap):
        t = el.find("./front/biblioData/title/mainTitle")
        title = re.sub(r"\s+", " ", (t.text or "")).strip() if t is not None else ""
        day = None
        if title:
            y = explicit_year(title)
            if y is not None and y < state["last"]:  # 확실한 연도라도 뒤로 가면 무시(목차·해제 속 연도)
                y = None
            guessed = False
            if y is None and (g := _GANJI_YEAR.search(title)) and (len(title) <= 14 or "年" in title or "日記" in title):
                mpos = _MONTH_FULL.search(title)
                dpos = _DAY_HEAD.match(title)
                # 「正月 小 壬寅」처럼 달 뒤에 붙은 간지는 그 달의 간지, 「初一日戊午」는 그날 일진 → 연도가 아니다
                if not ((mpos and g.start() > mpos.start()) or dpos):
                    y = _year_from_ganji(g[1], state["last"])
                    guessed = True
            if y and guessed and not (0 <= y - state["last"] <= 4):  # 일기는 한 해씩 앞으로 간다: 뒤로 가거나 크게 뛰면 연도로 보지 않는다
                y = None
            if y and y != year:
                year, month = y, None
                state["last"] = y
            if (dh := _DAY_HEAD.match(title)) is not None:
                if dh[2]:
                    month, leap = cn_num(dh[2]), bool(dh[1])
                day = day_num(dh[3], year, month, leap) if year and month else None
            elif (mh := _MONTH_FULL.search(title)) and len(title) <= 20:
                month, leap = cn_num(mh[2]), bool(mh[1])
        txt_el = el.find("text")
        if txt_el is not None and year and month:
            text, _ = _article_text(txt_el)
            if day:
                yield el.get("id"), title, SimpleNamespace(year=year, month=month, day=day, leap=leap,
                                                           day_ganji=None), text.strip(), []
            else:
                yield from split_days(el.get("id"), title, text, year, month, leap)
        for ch in el:
            if ch.tag.startswith("level"):
                yield from walk(ch, year, month, leap)

    yield from walk(root, None, None, False)


if __name__ == "__main__":
    t = time.perf_counter()
    r = load_sa(sys.argv[1], sys.argv[2])
    print({k: v for k, v in r.items() if k != "per_book"}, f"{time.perf_counter() - t:.1f}s")
    for k, v in r["per_book"].items():
        print(" ", k, v)
