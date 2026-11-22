"""웹용 내보내기: 작업 DB → web/data/*.json (음력 달마다 한 파일, 안에서 날짜별로 묶음).

    python3 -m sillok.export data/work.sqlite ../web/data 1592 1598

규칙: 국편 번역 산물(ref_title_ko 등)은 내보내지 않는다. 원문·자체 요약·메타데이터만 싣는다.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import time
from pathlib import Path

from hdate import describe
from hdate.lunar import LunarDate, lunar_to_jdn
from hdate.regnal import labels_for

from .category import GROUP_NAMES, GROUPS

BOOK_NAMES = {"wna": "선조실록", "wnb": "선조수정실록"}
NOTE_KINDS = ("원주", "교감주", "사론", "newchar")
SOURCE_URL = "https://sillok.history.go.kr/id/"
# 내보내기에 절대 들어가면 안 되는 키 (검사용)
FORBIDDEN_KEYS = frozenset({"ref_title_ko", "mainTitle", "title_ko"})


def month_key(y: int, m: int, leap: int) -> str:
    return f"{y}-{m:02d}{'L' if leap else ''}"


def _regnal(lu: LunarDate) -> list[dict]:
    return [{"king": r.king, "year": r.year, "ambiguous": r.ambiguous} for r in labels_for(lu)]


def date_info(jdn: int) -> dict:
    d = describe(jdn)
    out = d.as_dict()
    out["regnal"] = _regnal(d.lunar)
    return out


def _month_range(y: int, m: int, leap: int) -> tuple[int, int]:
    start = lunar_to_jdn(y, m, 1, bool(leap))
    for last in (30, 29):
        try:
            return start, lunar_to_jdn(y, m, last, bool(leap))
        except ValueError:
            continue
    raise ValueError((y, m, leap))


def _article(row: sqlite3.Row, notes: list, groups: list, summ: sqlite3.Row | None) -> dict:
    a = {
        "id": row["id"],
        "book": row["book"],
        "url": SOURCE_URL + row["id"],
        "precision": row["date_precision"],
        "lunar_day": row["lunar_day"],
        "day_ganji_src": row["day_ganji_src"],
        "jdn": row["jdn"],
        "jdn_status": row["jdn_status"],
        "needs_review": bool(row["needs_review"]),
        "text": row["text"],
        "notes": notes,
        "groups": groups,
        "sources": json.loads(row["sources"]),
        "summary": None,
    }
    if summ is not None:
        sents = json.loads(summ["sentences"])
        a["summary"] = {
            "title": summ["title"],
            "sentences": [{"text": s["text"],
                           "evidence": [[e["start"], e["end"]] for e in s["evidence"]]}
                          for s in sents],
            "commentary": json.loads(summ["commentary"]) if summ["commentary"] else [],
            "author": summ["author"],
            "review_status": summ["review_status"],
        }
    return a


def export(con: sqlite3.Connection, out: Path, y0: int, y1: int) -> dict:
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM article WHERE lunar_year BETWEEN ? AND ? AND lunar_month IS NOT NULL "
        "AND date_precision != 'none' "
        "ORDER BY lunar_year, lunar_month, lunar_leap, COALESCE(jdn, 0), id", (y0, y1)).fetchall()
    # 날짜를 정할 수 없는 기사(없는 윤달 등)는 검수 전까지 싣지 않는다
    skipped = con.execute("SELECT COUNT(*) FROM article WHERE lunar_year BETWEEN ? AND ? "
                          "AND (date_precision = 'none' OR lunar_month IS NULL)", (y0, y1)).fetchone()[0]
    ids = [r["id"] for r in rows]
    q = ",".join("?" * len(ids))
    notes: dict[str, list] = {}
    for r in con.execute(f"SELECT article_id, kind, start, end FROM span WHERE article_id IN ({q}) "
                         f"AND kind IN ({','.join('?' * len(NOTE_KINDS))}) ORDER BY start",
                         (*ids, *NOTE_KINDS)):
        notes.setdefault(r[0], []).append([r[1], r[2], r[3]])
    groups: dict[str, list] = {}
    for r in con.execute(f"SELECT article_id, grp FROM article_group WHERE article_id IN ({q}) "
                         "ORDER BY rank", ids):
        groups.setdefault(r[0], []).append(r[1])
    summ = {r["article_id"]: r for r in con.execute(
        f"SELECT * FROM summary WHERE article_id IN ({q}) AND review_status != 'rejected'", ids)}

    months: dict[str, dict] = {}
    for r in rows:
        key = month_key(r["lunar_year"], r["lunar_month"], r["lunar_leap"])
        m = months.get(key)
        if m is None:
            js, je = _month_range(r["lunar_year"], r["lunar_month"], r["lunar_leap"])
            first = describe(js)
            m = months[key] = {
                "key": key, "lunar": {"year": r["lunar_year"], "month": r["lunar_month"],
                                      "leap": bool(r["lunar_leap"])},
                "jdn_start": js, "jdn_end": je,
                "solar_start": first.solar.iso(), "solar_end": describe(je).solar.iso(),
                "regnal": _regnal(LunarDate(r["lunar_year"], r["lunar_month"], 1, bool(r["lunar_leap"]))),
                "ganji": {"year": first.year_ganji, "month": first.month_ganji},
                "days": {}, "month_articles": [],
            }
        a = _article(r, notes.get(r["id"], []), groups.get(r["id"], []), summ.get(r["id"]))
        if r["date_precision"] == "day":
            m["days"].setdefault(r["jdn"], []).append(a)
        else:
            m["month_articles"].append(a)

    if out.exists():
        shutil.rmtree(out)
    (out / "months").mkdir(parents=True)
    index_months = []
    keys = list(months)
    for i, key in enumerate(keys):
        m = months[key]
        days = [{"date": date_info(j), "articles": arts} for j, arts in sorted(m["days"].items())]
        doc = {**{k: v for k, v in m.items() if k != "days"}, "days": days,
               "prev": keys[i - 1] if i else None, "next": keys[i + 1] if i + 1 < len(keys) else None}
        _check(doc)
        (out / "months" / f"{key}.json").write_text(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        all_arts = [a for d in days for a in d["articles"]] + m["month_articles"]
        index_months.append({
            **{k: m[k] for k in ("key", "lunar", "jdn_start", "jdn_end", "solar_start", "solar_end",
                                 "regnal", "ganji")},
            "days": [{"jdn": d["date"]["jdn"], "solar": d["date"]["solar"],
                      "lunar_day": d["date"]["lunar"]["day"], "day_ganji": d["date"]["ganji"]["day"],
                      "n": len(d["articles"]),
                      "summarized": sum(a["summary"] is not None for a in d["articles"]),
                      "titles": [a["summary"]["title"] for a in d["articles"] if a["summary"]][:3]}
                     for d in days],
            "n_month": len(m["month_articles"]),
            "n": len(all_arts),
            "summarized": sum(a["summary"] is not None for a in all_arts),
        })
    index = {
        "years": [y0, y1],
        "books": BOOK_NAMES,
        "groups": [{"key": g, "name": n} for g, n, _ in GROUPS],
        "months": index_months,
        "n_articles": len(rows),
        "n_summarized": sum(m["summarized"] for m in index_months),
        "generated": time.strftime("%Y-%m-%d"),
    }
    _check(index)
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")),
                                    encoding="utf-8")
    return {"months": len(index_months), "articles": index["n_articles"],
            "summarized": index["n_summarized"], "skipped": skipped}


def _check(obj) -> None:
    """금지 키가 섞이지 않았는지 확인한다."""
    if isinstance(obj, dict):
        bad = FORBIDDEN_KEYS & obj.keys()
        if bad:
            raise ValueError(f"내보내기 금지 키: {bad}")
        for v in obj.values():
            _check(v)
    elif isinstance(obj, list):
        for v in obj:
            _check(v)


def main() -> None:
    p = argparse.ArgumentParser(prog="sillok.export")
    p.add_argument("db")
    p.add_argument("out")
    p.add_argument("y0", type=int)
    p.add_argument("y1", type=int)
    a = p.parse_args()
    t = time.perf_counter()
    r = export(sqlite3.connect(a.db), Path(a.out), a.y0, a.y1)
    print(r, f"{time.perf_counter() - t:.1f}s")


if __name__ == "__main__":
    main()
