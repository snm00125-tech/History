"""임진왜란 7년판 아티팩트용 데이터 묶음 (web/public/data → artifact/imjin/data).

    python3 tools/build_artifact_imjin.py data/work.sqlite ../web/public/data ../artifact/imjin

- 양력 1592-01 ~ 1599-02 달 파일을 그대로 복사(실록·쇄미록 등, 요약·인물 포함).
- index.json: 책 이름, 분류, 달 목록, 범위 안 주요 사건, 제목 목록(검색용, 한 파일).
- persons.json: 범위 안 기사에 나오는 인물(정보, 관직 기록 중 범위 안 것, 기사 목록).
- review.json: 범위 안 검수 묶음.
아티팩트 한도(파일 511개, 256MB) 안에 들어가도록 한 페이지 앱이 이 파일들만 읽는다.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

Y0, YM_END = 1592, "1599-02"


def main(db: str, src: str, out: str) -> None:
    srcp, outp = Path(src), Path(out)
    data = outp / "data"
    if data.exists():
        shutil.rmtree(data)
    (data / "m").mkdir(parents=True)
    idx = json.loads((srcp / "index.json").read_text(encoding="utf-8"))
    months = [m for m in idx["months"] if f"{Y0}-01" <= m["ym"] <= YM_END]
    titles, ids = [], set()
    for m in months:
        shutil.copy(srcp / "m" / f"{m['ym']}.json", data / "m" / f"{m['ym']}.json")
        mf = json.loads((srcp / "m" / f"{m['ym']}.json").read_text(encoding="utf-8"))
        for d in mf["days"]:
            for a in d["articles"]:
                titles.append([a["t"], d["solar"], a["id"], a["b"]])
                ids.add(a["id"])
        for a in mf["monthly"]:
            titles.append([a["t"], a["range"][0], a["id"], a["b"]])
            ids.add(a["id"])
    events = json.loads((srcp / "events.json").read_text(encoding="utf-8"))
    events = [e for e in events if f"{Y0}-01" <= e["solar"][:7] <= YM_END]
    books = {k: v for k, v in idx["books"].items() if any(t[3] == k for t in titles)}
    (data / "index.json").write_text(json.dumps(
        {"books": books, "groups": idx["groups"], "months": months, "events": events, "titles": titles},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    con = sqlite3.connect(db)
    doc_of = {t[2]: i for i, t in enumerate(titles)}
    persons: dict[str, dict] = {}
    for aid, pid in con.execute("SELECT article_id, person_id FROM article_person"):
        if aid in ids:
            persons.setdefault(pid, {"docs": []})["docs"].append(doc_of[aid])
    for pid in list(persons):
        row = con.execute("SELECT name_ko, name_hj, ja, ho, siho, bongwan, born, died, kind FROM person WHERE id=?",
                          (pid,)).fetchone()
        if not row:  # 인물 CSV에 없는 색인 번호(소수)
            del persons[pid]
    for pid, p in persons.items():
        ko, hj, ja, ho, siho, bon, born, died, kind = con.execute(
            "SELECT name_ko, name_hj, ja, ho, siho, bongwan, born, died, kind FROM person WHERE id=?", (pid,)).fetchone()
        p.update({k: v for k, v in (("ko", ko), ("hj", hj), ("ja", ja), ("ho", ho), ("siho", siho), ("bon", bon),
                                    ("born", born), ("died", died), ("kind", kind)) if v})
        p["docs"] = sorted(set(p["docs"]))
        p["off"] = [[aid, off, st] for aid, off, st in con.execute(
            "SELECT article_id, office, status FROM person_office WHERE person_id=? ORDER BY jdn", (pid,)) if aid in doc_of]
        p["off"] = [[doc_of[a], o, s] for a, o, s in p["off"]]
    (data / "persons.json").write_text(json.dumps(persons, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    review = json.loads((srcp / "review.json").read_text(encoding="utf-8"))
    review = [g for g in review if any(it["id"] in ids for it in g["items"])]
    (data / "review.json").write_text(json.dumps(review, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    files = list(data.rglob("*.json"))
    print({"months": len(months), "articles": len(titles), "events": len(events), "persons": len(persons),
           "review_groups": len(review), "files": len(files),
           "MB": round(sum(f.stat().st_size for f in files) / 1e6, 1)})


if __name__ == "__main__":
    main(*sys.argv[1:4])
