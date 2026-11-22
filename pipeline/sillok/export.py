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
from .category import GROUP_NAMES

EVENTS = Path(__file__).parents[1] / "events" / "joseon.json"


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


@lru_cache(maxsize=None)
def day_info(jdn: int) -> dict:
    d = describe(jdn)
    lun = d.lunar
    regs = labels_for(lun) if lun else []
    return {
        "jdn": jdn,
        "solar": f"{d.solar.year:04d}-{d.solar.month:02d}-{d.solar.day:02d}",
        "cal": "G" if d.solar.gregorian else "J",
        "lunar": f"{lun.year}-{lun.month:02d}-{lun.day:02d}" if lun else None,
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


def build_review(con, titles: dict, books: dict) -> list[dict]:
    """검수 대상(needs_review=1)을 (책, 음력 연·월, 윤, 상태, 차이) 묶음으로. 한 달이 통째로 밀린 경우가 한 묶음이 된다."""
    groups: dict[tuple, dict] = {}
    for aid, book, ly, lm, lp, ld, gz, j, jt, st, dl in con.execute(
            """SELECT id, book, lunar_year, lunar_month, lunar_leap, lunar_day, day_ganji_src, jdn, jdn_table,
                      jdn_status, ganji_delta FROM article WHERE needs_review=1 ORDER BY COALESCE(jdn, jdn_table), id"""):
        key = (book, ly, lm, lp, st, dl)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": f"{book}-{ly}-{lm}{'L' if lp else ''}-{st}-{dl}", "book": book,
                               "bookName": books.get(book, book), "lunarMonth": f"{ly}년 {'윤' if lp else ''}{lm}월",
                               "status": st, "label": REVIEW_LABEL.get(st, st), "delta": dl, "items": []}
        g["items"].append({"id": aid, "t": titles.get(aid, ""), "lunarDay": ld, "ganji": gz,
                           "solar": day_info(j)["solar"] if j else None,
                           "tableSolar": day_info(jt)["solar"] if jt else None})
    return sorted(groups.values(), key=lambda g: -len(g["items"]))


def _ym(jdn: int) -> tuple[str, str]:
    s = day_info(jdn)["solar"]
    return s[:7], s[5:]


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

    months: dict[str, dict] = defaultdict(lambda: {"days": defaultdict(list), "monthly": []})
    search_docs: list[tuple[str, str, str, str]] = []
    search_texts: list[str] = []
    otd: dict[str, list] = defaultdict(list)
    undated = []
    persons_of: dict[str, list] = defaultdict(list)
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='article_person'").fetchone():
        for aid, pid, ko in con.execute("""SELECT ap.article_id, ap.person_id, p.name_ko FROM article_person ap
                                           JOIN person p ON p.id = ap.person_id ORDER BY ap.article_id, ap.n DESC"""):
            if len(persons_of[aid]) < 12 and ko:
                persons_of[aid].append([pid, ko])
    rows = con.execute("""SELECT id, book, lunar_year, lunar_month, lunar_leap, date_precision,
                                 jdn_start, jdn_end, jdn_status, needs_review, text, regnal_src
                          FROM article ORDER BY jdn_start, book, id""")
    for aid, book, ly, lm, leap, prec, js, je, status, review, text, reg in rows:
        art = {"id": aid, "b": book, "t": titles.get(aid, ""), "g": groups.get(aid, []), "x": text}
        if reg and book.startswith("wz"):  # 고종·순종: 원자료 재위연도 표기를 왕력으로 쓴다(양력 시기 포함)
            art["reg"] = reg.split(" ")[0] + " " + reg.split(" ")[1]
        if aid in sums:
            art["s"] = sums[aid]
        if aid in persons_of:
            art["p"] = persons_of[aid]
        if review:
            art["r"] = status
        search_docs.append((art["t"], day_info(js)["solar"] if js is not None else "", aid, book))
        search_texts.append(text)
        if prec == "day":
            ym, md = _ym(js)
            months[ym]["days"][js].append(art)
            otd[md].append({"y": day_info(js)["solar"][:4], "id": aid, "b": book, "t": art["t"]})
        elif prec == "month" and js is not None:
            ym, _ = _ym(js)
            art["lunarMonth"] = f"{ly}-{lm:02d}" + ("(윤)" if leap else "")
            art["range"] = [day_info(js)["solar"], day_info(je)["solar"]]
            months[ym]["monthly"].append(art)
        else:
            art["lunarMonth"] = f"{ly}-{lm:02d}" if ly and lm else None
            undated.append(art)

    events = load_events(con)
    ev_by_jdn = defaultdict(list)
    for e in events:
        ev_by_jdn[e["jdn"]].append({"name": e["name"], "desc": e["desc"], "anchor": e["anchor"]})
        months[e["solar"][:7]]  # 사건만 있는 달도 파일을 만든다
    month_index = []
    for ym in sorted(months):
        m = months[ym]
        days = []
        for j in [j for j in ev_by_jdn if day_info(j)["solar"][:7] == ym and j not in m["days"]]:
            m["days"][j] = []
        for j, arts in sorted(m["days"].items()):
            info = dict(day_info(j))
            regs = list(dict.fromkeys(a["reg"] for a in arts if "reg" in a))
            if regs:  # 고종·순종은 원자료 표기가 우선
                info["regnal"] = regs
            if j in ev_by_jdn:
                info["events"] = ev_by_jdn[j]
            days.append({**info, "articles": arts})
        n = sum(len(d["articles"]) for d in days) + len(m["monthly"])
        (outp / "m" / f"{ym}.json").write_text(
            json.dumps({"ym": ym, "days": days, "monthly": m["monthly"]}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        kings = sorted({r.split()[0] for d in days for r in d["regnal"]})
        month_index.append({"ym": ym, "n": n, "kings": kings})
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
    review = build_review(con, titles, books)
    (outp / "review.json").write_text(json.dumps(review, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kings_full = build_kings(con, events)
    (outp / "kings.json").write_text(json.dumps(kings_full, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (outp / "events.json").write_text(json.dumps(events, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = {"books": books, "groups": GROUP_NAMES, "months": month_index, "kings": kings,
             "total": sum(mi["n"] for mi in month_index) + len(undated), "undated": len(undated),
             "summarized": len(sums)}
    (outp / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"months": len(month_index), "articles": index["total"], "search": search_stats, "fulltext": fulltext_stats, "persons": person_stats,
            "secs": round(time.perf_counter() - t0, 1)}


if __name__ == "__main__":
    print(export(sys.argv[1], sys.argv[2]))
