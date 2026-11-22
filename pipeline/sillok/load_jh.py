"""국편 근대 문서 자료 → 작업 DB.

  jh = 주한일본공사관기록(공공데이터 15053633, 1894~1910)
  hk = 한국근대사자료집성(공공데이터 15053628, 1880년대~1910년대)

    python3 -m sillok.load_jh data/raw data/work.sqlite [jh hk]

자료 구조(국편 khdb): level2 장 > level3 문서 > (level4 별지·첨부 문서). 문서마다 front/biblioData/date 아래
dateSend(발송)·dateReceived(접수)·dateContract·dateCreated·dateOccured가 있고, date 속성(YYYY-MM-DD, 9999 = 미상,
끝에 L0/L1이면 음력)과 원문 표기(明治二十七年五月十二日)가 함께 있다.

날짜 정하는 순서
1. 문서 자신의 날짜 칸: 발송 > 작성·계약·발생 > 접수. 원문 표기를 읽어(연호·간지·서양식) 속성과 대조한다.
   - 원문 표기에 해가 있고 속성과 다르면 원문 표기를 쓴다 → 'date_fixed'(검수). 예: 속성 1984-10-01, 표기 明治二十七年十月一日.
   - 표기에 달·날만 있으면(「二月十八日」「同二十三日」「我曆六月十二日」) 해·달은 속성 → 같은 문서의 앞 칸 → 앞 문서에서.
     속성에 해가 없어 앞 문서로 채우면 'year_inferred'(검수).
2. 날짜 칸이 없으면 본문의 발송일(pDate) → 본문 끝 300자·첫 150자의 연호 날짜(明治·光武 등 연호가 있는 것만).
3. 그래도 없고 첨부(level4)면 바탕 문서의 날짜 → 'parent'.
4. 없으면 precision none.
달력: 明治(6년 이후)·大正·光武·隆熙·建陽·서기·서양식 = 양력(그레고리력) → 'solar'.
開國·청 연호(光緒 등)·간지 해 = 음력(KASI 표) → 'lunar'. 속성에 L이 있어도 표기가 서양식이면 양력으로 본다(hk 프랑스어 문서).
해가 1850~1920 밖이면 버린다(속성 1984·1986 등 입력 오기).
제목: 국편 mainTitle(앞 번호 「(5)」「1)」는 뗌) → ref_title_ko.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from hdate import ganji, lunar
from hdate.calendar import solar_to_jdn
from hdate.lunar import jdn_to_lunar
from .load import SCHEMA
from .load_sa import BOOK_SCHEMA
from .parse import _article_text, _join_surrogates

SOURCES = {  # 책 코드 → (이름, 원자료 폴더, 파일 무늬)
    "jh": ("주한일본공사관기록", "khdb_15053633", "jh_*.xml"),
    "hk": ("한국근대사자료집성", "khdb_15053628", "hk_*.xml"),
}
YEAR_MIN, YEAR_MAX = 1850, 1920
DATE_PREF = ("dateSend", "dateCreated", "dateContract", "dateOccured", "dateIssued", "dateReceived")

# 연호 → (원년의 서기 연도 - 1, 달력)
ERAS = {"明治": (1867, "solar"), "大正": (1911, "solar"), "昭和": (1925, "solar"), "光武": (1896, "solar"),
        "隆熙": (1906, "solar"), "建陽": (1895, "solar"), "開國": (1391, "lunar"), "光緖": (1874, "lunar"),
        "光緒": (1874, "lunar"), "同治": (1861, "lunar"), "咸豐": (1850, "lunar"), "宣統": (1908, "lunar"),
        "慶應": (1864, "lunar"), "元治": (1863, "lunar")}
_DIG = {"〇": 0, "○": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_N = r"[〇○零一二三四五六七八九十廿卄卅百\d]+"
_GZ = "[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]"
_ERA_RE = "|".join(ERAS)
# 연호/간지/서기 + 年 + 月 + 日
_EAST = re.compile(rf"(?:(?P<era>{_ERA_RE})\s*(?P<ey>{_N}|元)\s*年|(?P<gz>{_GZ})\s*年?|(?P<ad>1[89]\d\d)\s*年|(?P<bare>{_N})\s*年)?"
                   rf"\s*(?P<leap>[閏潤])?\s*(?P<m>{_N}|正)\s*月\s*(?:(?P<d>(?:初|旬)?\s*{_N}|晦|朔)(?P<dend>\s*日|(?=[\s(（)）]|$)))?")
_MONTHS = {"jan": 1, "janvier": 1, "januar": 1, "january": 1, "feb": 2, "fév": 2, "fev": 2, "février": 2, "fevrier": 2,
           "februar": 2, "february": 2, "mar": 3, "mars": 3, "märz": 3, "march": 3, "apr": 4, "avr": 4, "avril": 4,
           "april": 4, "may": 5, "mai": 5, "jun": 6, "juin": 6, "juni": 6, "june": 6, "jul": 7, "juil": 7,
           "juillet": 7, "juli": 7, "july": 7, "aug": 8, "août": 8, "aout": 8, "august": 8, "sep": 9, "sept": 9,
           "septembre": 9, "september": 9, "oct": 10, "okt": 10, "octobre": 10, "oktober": 10, "october": 10,
           "nov": 11, "novembre": 11, "november": 11, "dec": 12, "déc": 12, "dez": 12, "décembre": 12,
           "decembre": 12, "dezember": 12, "december": 12}
_MON_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_Y2 = r"(\d{4}(?!\d)|[’'‘]\d\d|\d\d(?![\d:.]|th|st|nd|rd|\s*(?:a\.?m|p\.?m|Year)))"  # 2자리 해는 시각·서수가 아닐 때만
_WEST_DMY = re.compile(rf"(?<![\d/])(\d{{1,2}})(?:er|st|nd|rd|th|eme|ème)?\.?\s+({_MON_RE})\.?,?\s+{_Y2}", re.I)
_WEST_MDY = re.compile(rf"\b({_MON_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\.?,?\s+{_Y2}", re.I)
# 러시아 문서의 율리우스/그레고리 겹표기 「le 1/13 Juillet 1894」: 뒤(그레고리력)를 쓴다
_WEST_DUAL = re.compile(rf"(?<!\d)(\d{{1,2}})/(\d{{1,2}})\s+({_MON_RE})\.?,?\s+(\d{{4}})", re.I)
_WEST_DM = re.compile(rf"(?<![\d/.])(\d{{1,2}})(?:er|st|nd|rd|th|eme|ème)?\.?\s+({_MON_RE})\b", re.I)
_WEST_MD = re.compile(rf"\b({_MON_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?![.:]\d)", re.I)
_WEST_NUM = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2}),?\s*(1[89]\d\d)(?!\d)")  # 20/12, 1893 (일/월)
_ISO = re.compile(r"(?<!\d)(1[89]\d\d)[-./](\d{1,2})[-./](\d{1,2})(?!\d)")
_ATTR = re.compile(r"^(\d{4})-(\d\d)(?:-(\d\d))?(?:L([01]))?$")


def cn_int(s: str) -> int:
    """한자·아라비아 숫자 → 정수. 二十七·廿七·卅·旬二(=十二)·初六·３."""
    s = unicodedata.normalize("NFKC", s).replace(" ", "")
    s = s.removeprefix("初")
    if s.startswith("旬"):
        return 10 + cn_int(s[1:]) if len(s) > 1 else 10
    if s.isdigit():
        return int(s)
    s = s.replace("廿", "二十").replace("卄", "二十").replace("卅", "三十")
    n, cur = 0, 0
    for ch in s:
        if ch == "百":
            n += (cur or 1) * 100
            cur = 0
        elif ch == "十":
            n += (cur or 1) * 10
            cur = 0
        elif ch in _DIG:
            cur = cur * 10 + _DIG[ch]
        else:
            raise ValueError(s)
    return n + cur


def _gz_year(gz: str, near: int | None) -> int:
    gi = ganji.index_of(gz)
    near = near or 1900
    return min((y for y in range(near - 40, near + 41) if ganji.year_index(y) == gi), key=lambda y: abs(y - near))


def parse_date_text(s: str, near_year: int | None = None, era_hint: str | None = "明治"):
    """원문 날짜 표기 → dict(y, m, d, cal('solar'|'lunar'|None), leap, year_src). 못 읽으면 None.
    y·m·d는 없으면 None. year_src: era | ganji | ad | bare(연호 없는 「二十七年」→ era_hint) | None.
    cal None = 표기만으로는 달력을 모름(달·날만)."""
    if not s:
        return None
    s = unicodedata.normalize("NFC", s)
    if (m := _WEST_DUAL.search(s)) and (int(m[2]) - int(m[1]) in (12, 13) or int(m[2]) < int(m[1])):
        return dict(y=int(m[4]), m=_MONTHS[m[3].lower()], d=int(m[2]), cal="solar", leap=False, year_src="ad")
    for rx, order in ((_WEST_DMY, "dmy"), (_WEST_MDY, "mdy")):
        m = rx.search(s)
        if m:
            if order == "dmy":
                d, mo, y = int(m[1]), _MONTHS[m[2].lower()], int(m[3].lstrip("’'‘"))
            else:
                mo, d, y = _MONTHS[m[1].lower()], int(m[2]), int(m[3].lstrip("’'‘"))
            if y < 100:
                y += 1800 if y >= 50 else 1900
            return dict(y=y, m=mo, d=d, cal="solar", leap=False, year_src="ad")
    for rx, order in ((_WEST_DM, "dm"), (_WEST_MD, "md")):  # 해 없는 서양식(「Tokio, 17 Sept. 11.45 a.m.」)
        m = rx.search(s)
        if m:
            d, mo = (int(m[1]), _MONTHS[m[2].lower()]) if order == "dm" else (int(m[2]), _MONTHS[m[1].lower()])
            if 1 <= d <= 31:
                return dict(y=None, m=mo, d=d, cal="solar", leap=False, year_src=None)
    if (m := _WEST_NUM.search(s)) and 1 <= int(m[2]) <= 12:
        return dict(y=int(m[3]), m=int(m[2]), d=int(m[1]), cal="solar", leap=False, year_src="ad")
    if (m := _ISO.search(s)) and 1 <= int(m[2]) <= 12:
        return dict(y=int(m[1]), m=int(m[2]), d=int(m[3]), cal="solar", leap=False, year_src="ad")
    for m in _EAST.finditer(s):
        if not m["m"]:
            continue
        try:
            mo = 1 if m["m"] == "正" else cn_int(m["m"])
        except ValueError:
            continue
        if not 1 <= mo <= 12:
            continue
        y = cal = src = None
        if m["era"]:
            base, cal = ERAS[m["era"]]
            y, src = base + (1 if m["ey"] == "元" else cn_int(m["ey"])), "era"
            if m["era"] == "明治" and y < 1873:
                cal = "lunar"  # 일본은 明治6년(1873)부터 양력
        elif m["gz"]:
            y, cal, src = _gz_year(m["gz"], near_year), "lunar", "ganji"
        elif m["ad"]:
            y, cal, src = int(m["ad"]), "solar", "ad"
        elif m["bare"] and era_hint:
            n = cn_int(m["bare"])
            base, cal = ERAS[era_hint]
            y, src = base + n, "bare"
            if near_year and abs(y - near_year) > 3:  # 연호를 짐작할 수 없다
                y = cal = src = None
        d = None
        if m["d"]:
            if m["d"] == "朔":
                d = 1
            elif m["d"] == "晦":
                d = 0  # 그달 마지막 날(뒤에서 정함)
            else:
                try:
                    d = cn_int(m["d"])
                except ValueError:
                    d = None
            if d is not None and not 0 <= d <= 31:
                d = None
        if "我曆" in s or "陽曆" in s:
            cal = "solar"
        return dict(y=y, m=mo, d=d, cal=cal, leap=bool(m["leap"]), year_src=src)
    return None


def parse_attr(a: str | None):
    """속성 '1894-05-12'·'1888-11-02L0'·'9999-02-18' → dict(y|None, m|None, d|None, lunar, leap)."""
    m = _ATTR.match(a or "")
    if not m:
        return None
    y, mo, d = int(m[1]), int(m[2]), int(m[3]) if m[3] else None
    return dict(y=None if y in (0, 9999) else y, m=None if mo in (0, 99) or mo > 12 else mo,
                d=None if d in (None, 0, 99) or d > 31 else d, lunar=m[4] is not None, leap=m[4] == "1")


def to_range(y, m, d, cal, leap=False):
    """→ (precision, start, end, (lunar y, m, leap, d)) 또는 None(성립 안 함)."""
    if y is None or not YEAR_MIN <= y <= YEAR_MAX or m is None:
        return None
    try:
        if cal == "lunar":
            try:
                lunar.month_length(y, m, leap)
            except ValueError:
                leap = False
            n = lunar.month_length(y, m, leap)
            s = lunar.lunar_to_jdn(y, m, 1, leap)
            if d is None:
                return "month", s, s + n - 1, (y, m, leap, None)
            d = n if d == 0 else d
            if d > n:
                return None
            return "day", s + d - 1, s + d - 1, (y, m, leap, d)
        s = solar_to_jdn(y, m, 1)
        e = (solar_to_jdn(y + 1, 1, 1) if m == 12 else solar_to_jdn(y, m + 1, 1)) - 1
        if d is None:
            return "month", s, e, None
        d = e - s + 1 if d == 0 else d
        if s + d - 1 > e:
            return None
        return "day", s + d - 1, s + d - 1, None
    except ValueError:
        return None


def resolve(elems: list[tuple[str, str | None, str]], ctx: dict | None, era_hint="明治", support: dict | None = None):
    """문서 날짜 칸들 [(태그, 속성, 표기)] + 앞 문서 날짜 ctx → dict(y, m, d, cal, leap, status, review, how, r) 또는 None.
    ctx = 앞 문서에서 정한 dict(y, m, d, cal). support = 같은 장(level2) 문서 속성의 해별 개수."""
    order = sorted(elems, key=lambda e: DATE_PREF.index(e[0]) if e[0] in DATE_PREF else 99)
    attrs = [parse_attr(at) for _, at, _ in order]
    # 같은 문서의 다른 칸 속성(예: 발송 표기는 「我曆五月二十五日」뿐, 접수 속성 1894-06-28) → 해의 기준
    doc = next((dict(y=x["y"], m=x["m"], d=x["d"], cal="lunar" if x["lunar"] else "solar") for x in attrs
                if x and x["y"] and x["m"]), None)
    near = (doc or ctx or {}).get("y")
    for (tag, attr, txt), A in zip(order, attrs):
        a_full = bool(A and A["y"] and A["m"])
        T = parse_date_text(txt, (A and A["y"]) or near, era_hint)
        status, review = None, 0
        if T and T["y"] is not None and T["m"] is not None:  # 표기에 해까지 있다
            y, m, d, cal, leap = T["y"], T["m"], T["d"], T["cal"], T["leap"]
            if a_full and A["d"] and d is None:  # 표기의 날을 못 읽음(「十匕日」「八月九月一日」): 속성을 쓴다
                y, m, d, cal, leap = A["y"], A["m"], A["d"], "lunar" if A["lunar"] else "solar", A["leap"]
            elif (a_full and abs(y - A["y"]) >= 2 and support is not None and not support.get(y)
                    and support.get(A["y"], 0) >= 3 and YEAR_MIN <= A["y"] <= YEAR_MAX):
                # 표기의 해가 이 장의 다른 문서에 없고 속성의 해는 흔하다(「明治十四年」= 三 빠짐 등): 속성을 쓴다
                y, m, d, cal, leap = A["y"], A["m"], A["d"], "lunar" if A["lunar"] else "solar", A["leap"]
                status, review = "date_conflict", 1
            if status is None and a_full and cal == "solar" and (A["y"], A["m"], A["d"]) != (y, m, d) and (
                    not A["lunar"] or (A["m"], A["d"]) != (m, d)):
                status, review = "date_fixed", 1
        elif T and T["m"] is not None:  # 달·날만: 해는 이 칸 속성 → 같은 문서 다른 칸 → 앞 문서
            m, d, leap = T["m"], T["d"], T["leap"]
            cal = T["cal"] or ("lunar" if A and A["lunar"] else "solar")
            base = (A if A and A["y"] else None) or doc
            if base is None and ctx:
                base, status, review = ctx, "year_inferred", 1
            if base is None:
                continue
            y = base["y"]
            if base.get("m") and m < base["m"] - 6:  # 해를 넘김(12월 → 1월)
                y += 1
            elif base.get("m") and m > base["m"] + 6:
                y -= 1
        elif re.match(r"^\s*同", txt or "") and not a_full and ctx and not (A and A["y"] and A["y"] != ctx["y"]):
            # 「同 午後二時 接」「同二十三日」: 앞 문서와 같은 날·같은 달
            dm = re.match(rf"^\s*同\s*({_N})日", unicodedata.normalize("NFC", txt))
            y, m, cal, leap = ctx["y"], ctx["m"], ctx["cal"], ctx.get("leap", False)
            d = cn_int(dm[1]) if dm else ctx.get("d")
            status = "same_as_prev"
        elif a_full:
            y, m, d, leap = A["y"], A["m"], A["d"], A["leap"]
            west = bool(re.search(r"[A-Za-z]", txt or "")) and not re.search(r"lune|moon", txt or "", re.I)
            cal = "lunar" if A["lunar"] and not west else "solar"
            if A["lunar"] and west:
                status, review = "attr_unchecked", 1
        else:
            continue
        r = to_range(y, m, d, cal, leap)
        if r is None:
            continue
        return dict(y=y, m=m, d=d, cal=cal, leap=leap, status=status, review=review, how=tag, r=r)
    return None


def resolve_body(pdates: list[str], text: str, ctx: dict | None, era_hint="明治"):
    """날짜 칸이 없는 문서: 본문 발송일(pDate) → 본문 끝·첫머리의 연호 날짜."""
    near = ctx["y"] if ctx else None
    for p in pdates:
        r = resolve([("dateSend", None, p)], ctx, era_hint)
        if r:
            r["how"] = "pDate"
            return r
    for chunk in (text[-300:], text[:150]):
        for m in _EAST.finditer(unicodedata.normalize("NFC", chunk)):
            if not m["era"] or not m["d"]:
                continue
            T = parse_date_text(m[0], near, None)
            if T and T["y"]:
                r = to_range(T["y"], T["m"], T["d"], T["cal"], T["leap"])
                if r:
                    return dict(y=T["y"], m=T["m"], d=T["d"], cal=T["cal"], leap=T["leap"], status="body_text",
                                review=1, how="body", r=r)
    return None


_NUMPFX = re.compile(r"^\s*(?:【[^】]*】|\(\s*[\d\-]+\s*\)|\d+\)|[一二三四五六七八九十]+\.)\s*")


def clean_title(t: str) -> str:
    return re.sub(r"\s+", " ", _NUMPFX.sub("", t or "")).strip()


def _parse(path: Path):
    raw = path.read_bytes()
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return ET.fromstring(_join_surrogates(raw.decode("utf-8")))


def iter_docs(code: str, files: list[Path]):
    """→ dict(id, title, text, spans, f(날짜), file). 파일 순서대로 앞 문서 날짜(ctx)를 잇는다."""
    era_hint = "明治" if code == "jh" else None
    for path in files:
        root = _parse(path)
        ctx = None
        support: dict = {}

        def walk(el, parent):
            nonlocal ctx
            for ch in el:
                if not ch.tag.startswith("level"):
                    continue
                if ch.tag == "level2":  # 장이 바뀌면 앞 문서 날짜를 잇지 않는다
                    ctx = None
                    support.clear()
                    for d in ch.iter():
                        if d.tag in DATE_PREF and (pa := parse_attr(d.get("date"))) and pa["y"]:
                            support[pa["y"]] = support.get(pa["y"], 0) + 1
                txt = ch.find("text")
                mine = None
                t = ch.find("./front/biblioData/title/mainTitle")
                title = "".join(t.itertext()).strip() if t is not None else ""
                is_doc = ch.get("type") == "문서" or (ch.get("type") is None and ch.tag in ("level3", "level4")
                                                     and title not in ("해제", "범례", "목차"))
                if txt is not None and is_doc:
                    elems = [(d.tag, d.get("date"), "".join(d.itertext()).strip())
                             for d in ch.findall("./front/biblioData/date/*")]
                    r = resolve(elems, ctx, era_hint, support) if elems else None
                    text, spans = _article_text(txt)
                    if r is None:
                        pd = ["".join(p.itertext()).strip() for p in txt.iter("pDate")]
                        r = resolve_body(pd, text, ctx, era_hint)
                    if r is None and parent is not None:
                        r = dict(parent, status="parent", review=0, how="parent")
                    mine = r
                    if r and r["how"] not in ("parent",):
                        ctx = r
                    yield dict(id=ch.get("id"), title=clean_title(title),
                               text=text, spans=spans, date=r, file=path.name)
                yield from walk(ch, mine or parent)

        yield from walk(root, None)


def fields(r):
    """resolve 결과 → article 칸 (lunar_year, lunar_month, leap, lunar_day, jdn, status, review, precision, start, end)."""
    if r is None:
        return None, None, 0, None, None, "no_date", 0, "none", None, None
    prec, s, e, lun = r["r"]
    status = r["status"] or ("lunar" if r["cal"] == "lunar" else "solar")
    if prec == "month":
        status = r["status"] or ("lunar_month" if r["cal"] == "lunar" else "solar_month")
    if lun:
        ly, lm, lleap, ld = lun
    else:
        lu = jdn_to_lunar(s) if prec == "day" else None
        ly, lm, lleap, ld = (lu.year, lu.month, lu.leap, lu.day) if lu else (r["y"], r["m"], False, None)
    jdn = s if prec == "day" else None
    return ly, lm, int(lleap), ld, jdn, status, r["review"], prec, s, e


def load_jh(raw: str, db: str, codes=None) -> dict:
    con = sqlite3.connect(db)
    con.executescript(SCHEMA + BOOK_SCHEMA)
    stats = {}
    with con:
        for code, (name, folder, pat) in SOURCES.items():
            if codes and code not in codes:
                continue
            files = sorted((Path(raw) / folder / "x").glob(pat))
            if not files:
                continue
            for t in ("span", "ref_title_ko", "subject", "article_group"):
                con.execute(f"DELETE FROM {t} WHERE article_id IN (SELECT id FROM article WHERE book=?)", (code,))
            con.execute("DELETE FROM article WHERE book=?", (code,))
            con.execute("DELETE FROM book WHERE code=?", (code,))
            rows, titles, spans, seen = [], [], [], set()
            for a in iter_docs(code, files):
                if a["id"] in seen or not a["text"].strip():
                    continue
                seen.add(a["id"])
                ly, lm, lleap, ld, jdn, st, rv, prec, s, e = fields(a["date"])
                src = json.dumps({"how": a["date"]["how"]} if a["date"] else {}, ensure_ascii=False)
                rows.append((a["id"], code, ly, lm, lleap, ld, None, jdn, jdn, st, None, rv, prec, s, e, a["text"],
                             "[]", src, a["file"], None))
                if a["title"]:
                    titles.append((a["id"], a["title"]))
                spans += [(a["id"], sp.kind, sp.start, sp.end, sp.ref) for sp in a["spans"]]
            con.executemany("INSERT INTO article (id,book,lunar_year,lunar_month,lunar_leap,lunar_day,day_ganji_src,"
                            "jdn,jdn_table,jdn_status,ganji_delta,needs_review,date_precision,jdn_start,jdn_end,text,"
                            "subjects,sources,file,regnal_src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.executemany("INSERT INTO ref_title_ko VALUES (?,?)", titles)
            con.executemany("INSERT INTO span VALUES (?,?,?,?,?)", spans)
            con.execute("INSERT INTO book VALUES (?,?,?)", (code, name, "kh"))
            stats[code] = len(rows)
    con.close()
    return stats


if __name__ == "__main__":
    t = time.perf_counter()
    print(load_jh(sys.argv[1], sys.argv[2], tuple(sys.argv[3:]) or None), f"{time.perf_counter() - t:.1f}s")
