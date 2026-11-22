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

from .category import GROUP_NAMES

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
    otd: dict[str, list] = defaultdict(list)
    undated = []
    rows = con.execute("""SELECT id, book, lunar_year, lunar_month, lunar_leap, date_precision,
                                 jdn_start, jdn_end, jdn_status, needs_review, text, regnal_src
                          FROM article ORDER BY jdn_start, book, id""")
    for aid, book, ly, lm, leap, prec, js, je, status, review, text, reg in rows:
        art = {"id": aid, "b": book, "t": titles.get(aid, ""), "g": groups.get(aid, []), "x": text}
        if reg and book.startswith("wz"):  # 고종·순종: 원자료 재위연도 표기를 왕력으로 쓴다(양력 시기 포함)
            art["reg"] = reg.split(" ")[0] + " " + reg.split(" ")[1]
        if aid in sums:
            art["s"] = sums[aid]
        if review:
            art["r"] = status
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

    month_index = []
    for ym in sorted(months):
        m = months[ym]
        days = []
        for j, arts in sorted(m["days"].items()):
            info = dict(day_info(j))
            regs = list(dict.fromkeys(a["reg"] for a in arts if "reg" in a))
            if regs:  # 고종·순종은 원자료 표기가 우선
                info["regnal"] = regs
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
    index = {"books": books, "groups": GROUP_NAMES, "months": month_index, "kings": kings,
             "total": sum(mi["n"] for mi in month_index) + len(undated), "undated": len(undated),
             "summarized": len(sums)}
    (outp / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"months": len(month_index), "articles": index["total"], "secs": round(time.perf_counter() - t0, 1)}


if __name__ == "__main__":
    print(export(sys.argv[1], sys.argv[2]))
