"""작업 DB → 웹용 JSON 내보내기.

    python3 -m sillok.export data/work.sqlite ../web/public/data

출력 (양력 = 1582-10-15 이후 그레고리력, 이전 율리우스력):
  index.json            실록 이름, 분류 이름, 양력 달 목록(기사 수), 왕 목록
  m/YYYY-MM.json        그 양력 달의 날별 기사 (+ 그달에 몰아 적은 month 정밀도 기사)
  otd/MM-DD.json        같은 양력 월일의 기사 제목 (연도별, '오늘의 역사')
  undated.json          날짜를 정할 수 없는 기사
기사 제목은 국사편찬위원회 국문 제목(규칙 3, 개인판). 자체 요약이 있으면 함께 싣는다.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from hdate import describe
from hdate.regnal import labels_for

from hdate import lunar_to_jdn

from . import fulltext_index, search_index
from .export_person import export_persons
from .export_geo import export_geo
from .category import GROUP_NAMES

EVENTS = Path(__file__).parents[1] / "events" / "joseon.json"
TERMS = Path(__file__).parents[1] / "terms" / "joseon_terms.json"


def load_terms() -> list[dict]:
    return json.loads(TERMS.read_text(encoding="utf-8"))["terms"] if TERMS.exists() else []


def match_terms(title: str, terms_sorted: list[tuple[int, str]], avoid: list[str]) -> list[int]:
    """제목에서 용어를 긴 것부터 겹치지 않게 찾는다. 인물 이름과 겹치는 자리는 건너뛴다(예: 정언신 ≠ 정언)."""
    taken = [False] * len(title)
    for name in avoid:
        start = title.find(name)
        while name and start >= 0:
            for k in range(start, start + len(name)):
                taken[k] = True
            start = title.find(name, start + 1)
    found = []
    for i, t in terms_sorted:
        start = title.find(t)
        while start >= 0:
            if not any(taken[start:start + len(t)]):
                for k in range(start, start + len(t)):
                    taken[k] = True
                if i not in found:
                    found.append(i)
            start = title.find(t, start + 1)
    return sorted(found)


def load_events(con) -> list[dict]:
    """주요 사건: anchor 기사 날짜(또는 지정한 음력 날짜) → JDN. 설명은 해설(verified=false)."""
    if not EVENTS.exists():
        return []
    out = []
    for e in json.loads(EVENTS.read_text(encoding="utf-8"))["events"]:
        row = con.execute("SELECT jdn, jdn_start FROM article WHERE id=?", (e["anchor"],)).fetchone()
        if e.get("lunar"):
            y, m, d, lp = e["lunar"]
            j = lunar_to_jdn(y, m, d, lp)
        elif row and (row[0] or row[1]):
            j = row[0] or row[1]
        else:
            raise SystemExit(f"사건 날짜를 정할 수 없음: {e['name']} ({e['anchor']})")
        info = day_info(j)
        out.append({"name": e["name"], "era": e["era"], "desc": e["desc"], "anchor": e["anchor"], "jdn": j,
                    "solar": info["solar"], "lunar": info["lunar"], "regnal": info["regnal"], "verified": False})
    return sorted(out, key=lambda x: x["jdn"])

BOOKS = {
    "waa": "태조실록", "wba": "정종실록", "wca": "태종실록", "wda": "세종실록", "wea": "문종실록",
    "wfa": "단종실록", "wga": "세조실록", "wha": "예종실록", "wia": "성종실록", "wja": "연산군일기",
    "wka": "중종실록", "wla": "인종실록", "wma": "명종실록", "wna": "선조실록", "wnb": "선조수정실록",
    "woa": "광해군일기(중초본)", "wob": "광해군일기(정초본)", "wpa": "인조실록", "wqa": "효종실록",
    "wra": "현종실록", "wrb": "현종개수실록", "wsa": "숙종실록", "wsb": "숙종실록보궐정오",
    "wta": "경종실록", "wtb": "경종수정실록", "wua": "영조실록", "wva": "정조실록", "wwa": "순조실록",
    "wxa": "헌종실록", "wya": "철종실록", "wza": "고종실록", "wzb": "순종실록", "wzc": "순종실록부록",
    "bb": "비변사등록",
}


from hdate.lunar import FIRST_JDN as FIRST_LUNAR_JDN  # noqa: E402

JOSEON_REGNAL_END = 2417777  # 1907-07-20(그레고리력): 고종 양위 다음 날. 이후는 원자료 표기(순종)만

KH_BOOKS = ("sg", "kr", "kj", "th", "ko", "dh")  # 삼국사기·고려사·고려사절요·국편 연표 (load_kh)


NO_FULLTEXT = ("sjw",)  # 원문 색인에서 뺀 책(승정원일기 270만 건: 색인 크기·메모리)
NO_OTD = ("sjw",)  # 「오늘의 실록」에서 뺀 책
YEAR_FILE_BEFORE, YEAR_FILE_AFTER = 1392, 1910  # 이 밖의 연도는 달 파일을 해 파일 y/<연>.json으로 묶는다


def year_file(y: int) -> bool:
    return y < YEAR_FILE_BEFORE or y > YEAR_FILE_AFTER


def ym_key(ym: str) -> tuple[int, int]:
    return int(ym[:-3]), int(ym[-2:])


def ystr(y: int) -> str:
    """천문 연도 → 화면 문자열. 기원전은 '-057'(= 기원전 57년)로 자릿수를 맞춘다."""
    return f"{y:04d}" if y > 0 else f"-{1 - y:03d}"


@lru_cache(maxsize=None)
def day_info(jdn: int) -> dict:
    d = describe(jdn)
    lun = d.lunar
    regs = labels_for(lun) if lun and lun.year >= 1392 and jdn < JOSEON_REGNAL_END else []
    return {
        "jdn": jdn,
        "solar": f"{ystr(d.solar.year)}-{d.solar.month:02d}-{d.solar.day:02d}",
        "cal": "G" if d.solar.gregorian else "J",
        "lunar": f"{ystr(lun.year)}-{lun.month:02d}-{lun.day:02d}" if lun else None,
        **({"est": True} if d.lunar_estimated else {}),
        "leap": bool(lun and lun.leap),
        "regnal": [f"{r.king} {'즉위년' if r.year == 0 else f'{r.year}년'}" for r in regs],
        "ganji": [d.year_ganji, d.month_ganji, d.day_ganji],
    }


# 왕 → 그 왕의 실록 (재위 범위·기사 수를 이 실록 기사로 잡는다)
KING_BOOKS = [
    ("태조", "waa"), ("정종", "wba"), ("태종", "wca"), ("세종", "wda"), ("문종", "wea"), ("단종", "wfa"),
    ("세조", "wga"), ("예종", "wha"), ("성종", "wia"), ("연산군", "wja"), ("중종", "wka"), ("인종", "wla"),
    ("명종", "wma"), ("선조", "wna"), ("광해군", "woa"), ("인조", "wpa"), ("효종", "wqa"), ("현종", "wra"),
    ("숙종", "wsa"), ("경종", "wta"), ("영조", "wua"), ("정조", "wva"), ("순조", "wwa"), ("헌종", "wxa"),
    ("철종", "wya"), ("고종", "wza"), ("순종", "wzb"),
]


def build_kings(con, events: list[dict]) -> list[dict]:
    """왕별: 그 왕 실록의 첫·끝 날짜 기사, 기사 수, 양력 연도별 기사 수(모든 자료), 재위 중 주요 사건."""
    out = []
    for king, book in KING_BOOKS:
        r = con.execute("SELECT MIN(jdn_start), MAX(jdn_end), COUNT(*) FROM article WHERE book=? AND jdn_start IS NOT NULL",
                        (book,)).fetchone()
        if not r[0]:
            continue
        j0, j1, n = r
        y0, y1 = int(day_info(j0)["solar"][:4]), int(day_info(j1)["solar"][:4])
        out.append({"king": king, "book": book, "start": day_info(j0)["solar"], "end": day_info(j1)["solar"],
                    "jdnStart": j0, "jdnEnd": j1, "articles": n, "years": {},
                    "events": [{"name": e["name"], "solar": e["solar"]} for e in events if j0 <= e["jdn"] <= j1]})
    # 연도별 기사 수: 그 왕 실록 기사만 (다른 자료와 섞지 않는다)
    for k in out:
        years: dict[int, int] = defaultdict(int)
        for (j,) in con.execute("SELECT jdn_start FROM article WHERE book=? AND jdn_start IS NOT NULL", (k["book"],)):
            years[int(day_info(j)["solar"][:4])] += 1
        k["years"] = {str(y): years[y] for y in sorted(years)}
    return out


FULLTEXT = True  # 원문 본문 색인(약 7분). 빠르게 다시 내보낼 때는 False

REVIEW_LABEL = {"ganji_adjusted": "일진에 맞춰 날짜 조정", "ganji_conflict": "일진 불일치(표 날짜 유지)",
                "invalid_date": "날짜 오류(표에 없는 날)"}


RULE_LABEL = {
    "month_shift": "달 전체가 같은 날수만큼 밀림 → 달 경계 차이로 확정",
    "month_edge": "달 앞·뒤만 밀림 → 큰달·작은달 차이로 확정",
    "month_all_dated": "그 달 모든 날이 같은 차이 → 확정",
    "ganji_typo": "그 달 다른 날은 맞음 → 머리 일진 오기, 표 날짜 확정",
    "ganji_month_error": "한 달 내내 같은 큰 차이 → 원자료 간지 오류, 표 날짜 확정",
    "isolated": "하루만 어긋남 → 일진 오기인지 날짜 오기인지 사람 확인 필요",
    "no_such_day": "표에 없는 날 → 그 달 단위로 배치, 사람 확인 필요",
}


def build_review(con, titles: dict, books: dict) -> list[dict]:
    """검수 대상(needs_review=1)을 (책, 음력 연·월, 윤, 상태, 차이) 묶음으로. 한 달이 통째로 밀린 경우가 한 묶음이 된다."""
    groups: dict[tuple, dict] = {}
    has_rule = "review_rule" in [r[1] for r in con.execute("PRAGMA table_info(article)")]
    rule_col = "review_rule" if has_rule else "NULL"
    for aid, book, ly, lm, lp, ld, gz, j, jt, st, dl, rule, open_ in con.execute(
            f"""SELECT id, book, lunar_year, lunar_month, lunar_leap, lunar_day, day_ganji_src, jdn, jdn_table,
                      jdn_status, ganji_delta, {rule_col}, needs_review FROM article
                WHERE jdn_status IN ('ganji_adjusted','ganji_conflict','invalid_date')
                ORDER BY COALESCE(jdn, jdn_table, jdn_start), id"""):
        key = (book, ly, lm, lp, st, dl, rule)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": f"{book}-{ly}-{lm}{'L' if lp else ''}-{st}-{dl}-{rule}", "book": book,
                               "bookName": books.get(book, book), "lunarMonth": f"{ly}년 {'윤' if lp else ''}{lm}월",
                               "status": st, "label": REVIEW_LABEL.get(st, st), "delta": dl, "items": [],
                               "rule": rule, "ruleLabel": RULE_LABEL.get(rule, ""), "open": bool(open_)}
        g["items"].append({"id": aid, "t": titles.get(aid, ""), "lunarDay": ld, "ganji": gz,
                           "solar": day_info(j)["solar"] if j else None,
                           "tableSolar": day_info(jt)["solar"] if jt else None})
    return sorted(groups.values(), key=lambda g: (not g["open"], -len(g["items"])))


def _ym(jdn: int) -> tuple[str, str]:
    s = day_info(jdn)["solar"]
    return s[:7], s[5:]


# 연도 도식: 자료 묶음 8개(고정 순서 = 색 순서)
SERIES = [("sillok", "조선왕조실록"), ("sjw", "승정원일기"), ("bb", "비변사등록"), ("goryeo", "고려사·고려사절요"),
          ("ancient", "삼국사기·고대 사료"), ("diary", "일기·국조보감"), ("modern", "근현대 문서"), ("th", "국편 연표")]
_SERIES_OF = {"sjw": 1, "bb": 2, "kr": 3, "kj": 3, "sg": 4, "ko": 4, "gjbg": 5, "jh": 6, "hk": 6, "dh": 6, "th": 7}


def series_of(book: str) -> int:
    if book.startswith("w"):
        return 0
    if book.startswith("sa"):
        return 5
    return _SERIES_OF.get(book, 5)


# 왕조 띠: 통설 연대(교과서 기준). 줄(lane)이 같으면 같은 줄에 그린다.
DYNASTIES = [
    {"name": "고조선", "lane": 0, "start": -2333, "end": -108, "note": "건국 연대는 전승"},
    {"name": "고구려", "lane": 0, "start": -37, "end": 668},
    {"name": "백제", "lane": 1, "start": -18, "end": 660},
    {"name": "신라", "lane": 2, "start": -57, "end": 935},
    {"name": "발해", "lane": 0, "start": 698, "end": 926},
    {"name": "고려", "lane": 1, "start": 918, "end": 1392},
    {"name": "조선", "lane": 1, "start": 1392, "end": 1897},
    {"name": "대한제국", "lane": 1, "start": 1897, "end": 1910},
    {"name": "일제강점기", "lane": 1, "start": 1910, "end": 1945},
    {"name": "미군정", "lane": 1, "start": 1945, "end": 1948},
    {"name": "대한민국", "lane": 1, "start": 1948, "end": 2008},
]


def build_timeline(con, year_counts, group_counts, events, th_major, kings_full) -> dict:
    years = sorted(year_counts)
    y0, y1 = years[0], years[-1]
    span = [y for y in range(y0, y1 + 1) if y != 0]  # 0년 없음
    counts = [[year_counts.get(y, [0] * len(SERIES))[i] for y in span] for i in range(len(SERIES))]
    groups = {g: [group_counts.get(y, {}).get(g, 0) for y in span] for g in GROUP_NAMES}
    # 왕: 조선은 kings.json(그 왕 실록 첫~끝 기사), 고려·삼국은 원자료 왕력의 첫~끝 기사
    kings = [{"dyn": "조선", "name": k["king"], "start": int(k["start"][:-6]), "end": int(k["end"][:-6])}
             for k in kings_full]
    rng: dict[str, list[int]] = {}
    for reg, js, je in con.execute("""SELECT regnal_src, MIN(jdn_start), MAX(jdn_end) FROM article
                                      WHERE book IN ('kr','kj','sg') AND regnal_src IS NOT NULL
                                      AND jdn_start IS NOT NULL GROUP BY regnal_src"""):
        k = " ".join(reg.split()[:-1])
        r = rng.setdefault(k, [js, je])
        r[0], r[1] = min(r[0], js), max(r[1], je)
    for k, (js, je) in rng.items():
        dyn, name = k.split(" ", 1)
        kings.append({"dyn": dyn, "name": name, "start": int(day_info(js)["solar"][:-6]),
                      "end": int(day_info(je)["solar"][:-6])})
    evs = [{"name": e["name"], "solar": e["solar"], "src": "app"} for e in events] + th_major
    return {"years": [y0, y1], "series": [{"key": k, "name": n} for k, n in SERIES], "counts": counts,
            "groups": groups, "dynasties": DYNASTIES, "kings": sorted(kings, key=lambda k: k["start"]),
            "events": sorted(evs, key=lambda e: tuple(int(x) for x in re.match(r"(-?\d+)-(\d+)-(\d+)", e["solar"]).groups()))}


def export(db: str, out: str) -> dict:
    t0 = time.perf_counter()
    con = sqlite3.connect(db)
    outp = Path(out)
    if outp.exists():
        shutil.rmtree(outp)
    (outp / "m").mkdir(parents=True)
    (outp / "otd").mkdir()

    groups = defaultdict(list)
    for aid, g in con.execute("SELECT article_id, grp FROM article_group ORDER BY article_id, rank"):
        groups[aid].append(g)
    titles = dict(con.execute("SELECT article_id, title FROM ref_title_ko"))
    books = dict(BOOKS)
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='book'").fetchone():
        books.update(dict(con.execute("SELECT code, name FROM book")))
    sums = {}
    for aid, t, s, c, au in con.execute("SELECT article_id, title, sentences, commentary, author FROM summary"):
        sums[aid] = {"title": t, "sentences": [x["text"] for x in json.loads(s)],
                     "commentary": [x["text"] for x in json.loads(c or "[]")], "author": au}

    search_docs: list[tuple[str, str, str, str]] = []
    search_texts: list[str] = []
    otd: dict[str, list] = defaultdict(list)
    undated = []
    terms = load_terms()
    terms_sorted = sorted(enumerate(t["t"] for t in terms), key=lambda x: -len(x[1]))
    persons_of: dict[str, list] = defaultdict(list)
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='article_person'").fetchone():
        for aid, pid, ko in con.execute("""SELECT ap.article_id, ap.person_id, p.name_ko FROM article_person ap
                                           JOIN person p ON p.id = ap.person_id ORDER BY ap.article_id, ap.n DESC"""):
            if len(persons_of[aid]) < 12 and ko:
                persons_of[aid].append([pid, ko])
    events = load_events(con)
    ev_by_jdn = defaultdict(list)
    for e in events:
        ev_by_jdn[e["jdn"]].append({"name": e["name"], "desc": e["desc"], "anchor": e["anchor"]})
    ev_months = sorted({day_info(j)["solar"][:7] for j in ev_by_jdn}, key=ym_key)
    (outp / "y").mkdir()
    month_index = []
    lunar_src: dict[int, str] = {}  # 1000년 이전 날: 원자료 음력 표기(추정 역법보다 우선)
    year_buf: dict[str, dict] = {}
    year_cur = [None]

    def flush_year():
        if year_cur[0] is not None and year_buf:
            (outp / "y" / f"{year_cur[0]}.json").write_text(
                json.dumps(year_buf, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        year_buf.clear()

    def write_month(ym, m):
        days = []
        for j in [j for j in ev_by_jdn if day_info(j)["solar"][:7] == ym and j not in m["days"]]:
            m["days"][j] = []
        for j, arts in sorted(m["days"].items()):
            info = dict(day_info(j))
            if j in lunar_src:  # 원자료 음력 (예: 고려사 918~999)
                ls = lunar_src.pop(j)
                info["lunar"], info["leap"] = ls.rstrip("윤"), ls.endswith("윤")
                info.pop("est", None)
            regs = list(dict.fromkeys(a["reg"] for a in arts if "reg" in a))
            if regs:  # 고종·순종·고려·삼국은 원자료 표기가 우선
                info["regnal"] = regs
            if j in ev_by_jdn:
                info["events"] = ev_by_jdn[j]
            days.append({**info, "articles": arts})
        n = sum(len(d["articles"]) for d in days) + len(m["monthly"])
        obj = {"ym": ym, "days": days, "monthly": m["monthly"]}
        y = ym[:-3]
        if year_file(int(y)):
            if year_cur[0] != y:
                flush_year()
                year_cur[0] = y
            year_buf[ym] = obj
        else:
            (outp / "m" / f"{ym}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                                                 encoding="utf-8")
        kings = sorted({" ".join(r.split()[:-1]) for d in days for r in d["regnal"]})
        month_index.append({"ym": ym, "n": n, "kings": kings})

    def new_month():
        return {"days": defaultdict(list), "monthly": []}

    cur_ym, cur = None, new_month()

    def advance(ym):
        nonlocal cur_ym, cur
        if ym == cur_ym:
            return
        if cur_ym is not None:
            write_month(cur_ym, cur)
        while ev_months and ym_key(ev_months[0]) <= ym_key(ym):  # 사건만 있는 달도 파일을 만든다
            e = ev_months.pop(0)
            if e != ym and e != cur_ym:
                write_month(e, new_month())
        cur_ym, cur = ym, new_month()

    year_counts: dict[int, list[int]] = defaultdict(lambda: [0] * len(SERIES))
    group_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    th_major: list[dict] = []
    rows = con.execute("""SELECT id, book, lunar_year, lunar_month, lunar_leap, date_precision,
                                 jdn_start, jdn_end, jdn_status, needs_review, text, regnal_src, sources, lunar_day
                          FROM article ORDER BY jdn_start, book, id""")
    for aid, book, ly, lm, leap, prec, js, je, status, review, text, reg, srcs, ld in rows:
        art = {"id": aid, "b": book, "t": titles.get(aid, ""), "g": groups.get(aid, []), "x": text}
        if reg and book.startswith("wz"):  # 고종·순종: 원자료 재위연도 표기를 왕력으로 쓴다(양력 시기 포함)
            art["reg"] = reg.split(" ")[0] + " " + reg.split(" ")[1]
        elif reg and book in KH_BOOKS:
            art["reg"] = reg
        if status.startswith("est_"):
            art["e"] = 1  # 날짜가 추정 역법(1000년 이전)
        if book == "th" and srcs.startswith("{") and json.loads(srcs).get("imp") == "1":
            art["imp"] = 1  # 국편 연표 중요도 1
        if aid in sums:
            art["s"] = sums[aid]
        if aid in persons_of:
            art["p"] = persons_of[aid]
        if book != "sjw":
            ks = match_terms(art["t"], terms_sorted, [n for _, n in persons_of.get(aid, [])])
            if ks:
                art["k"] = ks
        if review:
            art["r"] = status
        if js is not None:
            sol = day_info(js)["solar"]
            yy = int(sol[:-6])
            year_counts[yy][series_of(book)] += 1
            for g in art["g"]:
                group_counts[yy][g] += 1
            if art.get("imp"):
                th_major.append({"name": art["t"], "solar": sol, "src": "th"})
        search_docs.append((art["t"], day_info(js)["solar"] if js is not None else "", aid, book))
        search_texts.append("" if book in NO_FULLTEXT else text)
        if prec == "day":
            if status == "solar_src" and js < FIRST_LUNAR_JDN and ly is not None:
                lunar_src.setdefault(js, f"{ystr(ly)}-{lm:02d}-{ld:02d}" + ("윤" if leap else ""))
            ym, md = _ym(js)
            advance(ym)
            cur["days"][js].append(art)
            if book not in NO_OTD:
                otd[md].append({"y": day_info(js)["solar"][:4], "id": aid, "b": book, "t": art["t"]})
        elif prec in ("month", "year") and js is not None:
            ym, _ = _ym(js)
            advance(ym)
            art["lunarMonth"] = (f"{ystr(ly)}-{lm:02d}" + ("(윤)" if leap else "")) if prec == "month" \
                else f"{ystr(ly)}년(달 미상)"
            art["range"] = [day_info(js)["solar"], day_info(je)["solar"]]
            cur["monthly"].append(art)
        else:
            art["lunarMonth"] = f"{ystr(ly)}-{lm:02d}" if ly and lm else None
            undated.append(art)
    if cur_ym is not None:
        write_month(cur_ym, cur)
    for e in ev_months:
        write_month(e, new_month())
    flush_year()
    for md, items in otd.items():
        (outp / "otd" / f"{md}.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")),
                                                 encoding="utf-8")
    (outp / "undated.json").write_text(json.dumps(undated, ensure_ascii=False, separators=(",", ":")),
                                       encoding="utf-8")
    kings = []
    for mi in month_index:
        for k in mi["kings"]:
            if not kings or kings[-1]["king"] != k:
                if any(x["king"] == k for x in kings):
                    continue
                kings.append({"king": k, "first": mi["ym"]})
    search_stats = search_index.build(search_docs, outp / "s")
    fulltext_stats = fulltext_index.build(search_texts, outp / "f") if FULLTEXT else {}
    doc_of = {d[2]: i for i, d in enumerate(search_docs)}
    person_stats = export_persons(con, outp, doc_of, lambda j: day_info(j)["solar"])
    geo_stats = export_geo(con, outp, doc_of, search_docs)
    (outp / "terms.json").write_text(json.dumps([{**t, "verified": False} for t in terms], ensure_ascii=False,
                                                separators=(",", ":")), encoding="utf-8")
    review = build_review(con, titles, books)
    (outp / "review.json").write_text(json.dumps(review, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kings_full = build_kings(con, events)
    (outp / "kings.json").write_text(json.dumps(kings_full, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (outp / "events.json").write_text(json.dumps(events, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tl = build_timeline(con, year_counts, group_counts, events, th_major, kings_full)
    (outp / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = {"books": books, "groups": GROUP_NAMES, "months": month_index, "kings": kings,
             "yearFile": [YEAR_FILE_BEFORE, YEAR_FILE_AFTER],
             "total": sum(mi["n"] for mi in month_index) + len(undated), "undated": len(undated),
             "summarized": len(sums)}
    (outp / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"months": len(month_index), "articles": index["total"], "search": search_stats, "fulltext": fulltext_stats, "persons": person_stats, "geo": geo_stats,
            "secs": round(time.perf_counter() - t0, 1)}


if __name__ == "__main__":
    print(export(sys.argv[1], sys.argv[2]))
