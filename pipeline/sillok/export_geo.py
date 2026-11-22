"""지도용 내보내기: 지명 좌표(geo/places.json, tools/build_gazetteer.py) × 원문 지명 색인 → data/geo/.

  geo/places.json   [{i, h, ko, lat, lon, kind, n, qid, cands, dec: {10년대: 언급 수}}]   (점으로 그릴 지명만)
  geo/states.json   나라 이름(倭·明 …) 언급 수 — 지도에 점이 아니라 목록으로
  geo/d/<k>.json    {지명 번호: [[연, 문서 번호], ...]} — 지명 40개씩 묶음. 문서 번호 = 제목 검색 문서 번호
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

PLACES = Path(__file__).parents[1] / "geo" / "places.json"
CHUNK = 40


def export_geo(con, outp: Path, doc_of: dict[str, int], docs: list) -> dict:
    if not PLACES.exists():
        return {}
    places = json.loads(PLACES.read_text(encoding="utf-8"))["places"]
    pts = [p for p in places if p["kind"] in ("place", "province")]
    num = {p["h"]: i for i, p in enumerate(pts)}
    states = {p["h"]: p for p in places if p["kind"] == "state"}
    hits: dict[int, list] = defaultdict(list)
    state_n: dict[str, int] = defaultdict(int)
    seen = set()
    for aid, name in con.execute("""SELECT s.article_id, substr(a.text, s.start+1, s.end-s.start)
                                    FROM span s JOIN article a ON a.id = s.article_id
                                    WHERE s.kind='index:지명'"""):
        if name in states:
            state_n[name] += 1
            continue
        i = num.get(name)
        d = doc_of.get(aid)
        if i is None or d is None or (i, d) in seen:
            continue
        seen.add((i, d))
        solar = docs[d][1]
        if not solar:
            continue
        y = int(solar[:-6])
        hits[i].append((y, d))
    out_places = []
    for i, p in enumerate(pts):
        dec: dict[int, int] = defaultdict(int)
        for y, _ in hits[i]:
            dec[(y // 10) * 10] += 1
        out_places.append({"i": i, "h": p["h"], "ko": p.get("ko"), "lat": p["lat"], "lon": p["lon"], "kind": p["kind"],
                           "qid": p.get("qid"), "cands": p.get("cands", 1), "n": len(hits[i]),
                           "dec": dict(sorted(dec.items()))})
    g = outp / "geo"
    (g / "d").mkdir(parents=True, exist_ok=True)
    (g / "places.json").write_text(json.dumps(out_places, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (g / "states.json").write_text(json.dumps(
        sorted([{"h": h, "ko": states[h].get("ko"), "n": n} for h, n in state_n.items()], key=lambda x: -x["n"]),
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for k in range(0, len(pts), CHUNK):
        chunk = {i: sorted(hits[i]) for i in range(k, min(k + CHUNK, len(pts)))}
        (g / "d" / f"{k // CHUNK}.json").write_text(json.dumps(chunk, separators=(",", ":")), encoding="utf-8")
    return {"places": len(pts), "mentions": sum(len(v) for v in hits.values()), "files": len(pts) // CHUNK + 3}


def docs_from_db(con):
    """export.py와 같은 순서로 문서 번호를 다시 만든다(지도만 빨리 다시 내보낼 때)."""
    from .export import day_info
    docs, doc_of = [], {}
    for aid, js in con.execute("SELECT id, jdn_start FROM article ORDER BY jdn_start, book, id"):
        doc_of[aid] = len(docs)
        docs.append(("", day_info(js)["solar"] if js is not None else "", aid, ""))
    return doc_of, docs


if __name__ == "__main__":
    import sqlite3
    import sys
    import time
    t = time.perf_counter()
    con = sqlite3.connect(sys.argv[1])
    doc_of, docs = docs_from_db(con)
    print(export_geo(con, Path(sys.argv[2]), doc_of, docs), f"{time.perf_counter() - t:.1f}s")
