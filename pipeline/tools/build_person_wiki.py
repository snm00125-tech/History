"""인물 배경·초상: 위키데이터·한국어 위키백과·위키미디어 공용 → persons/wiki.json (git에 넣는다).

    python3 tools/build_person_wiki.py data/work.sqlite [상위 N=5000]

- 기사에 많이 나오는 인물 N명(국편 인물 정보) 중 생년·몰년이 있는 사람만.
- 위키데이터 사람(Q5) 중 한국어 이름이 같고 생년 또는 몰년이 ±1년 안에서 맞는 항목만 잇는다(둘 다 맞는 것 우선,
  그래도 여럿이면 버림). 추측해서 잇지 않는다.
- 위키백과 요약(첫 문단, CC BY-SA 4.0)과 문서 주소, 초상(P18)의 공용 파일 정보(저작권·작가·작은 그림 주소)를 저장한다.
  그림 파일은 저장하지 않고 공용 서버 주소로 보여 준다.
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parents[1]
OUT = ROOT / "persons" / "wiki.json"
UA = "HistoryTimelinePersonal/1.0 (personal non-commercial history app)"


def get_json(url: str, data: bytes | None = None, accept="application/json", tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            wait = 5 * (i + 1) if e.code in (429, 503) else 3
            print(f"  {e.code} 재시도 {i + 1} ({wait}s)", flush=True)
            time.sleep(wait)
        except Exception as e:
            print("  재시도", i + 1, e, flush=True)
            time.sleep(3 * (i + 1))
    return None


def sparql(q: str) -> list[dict]:
    r = get_json("https://query.wikidata.org/sparql", urllib.parse.urlencode({"query": q}).encode(),
                 "application/sparql-results+json")
    return r["results"]["bindings"] if r else []


def year(v: str | None) -> int | None:
    m = re.match(r"([+-]?\d{1,4})-", v or "")
    return int(m[1]) if m else None


def strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def build(db: str, top: int = 5000) -> dict:
    con = sqlite3.connect(db)
    people = con.execute("""SELECT p.id, p.name_ko, p.name_hj, p.born, p.died, COUNT(*) c FROM article_person ap
                            JOIN person p ON p.id = ap.person_id GROUP BY p.id ORDER BY c DESC LIMIT ?""", (top,)).fetchall()
    people = [p for p in people if p[1] and (p[3] or p[4])]
    by_name: dict[str, list] = {}
    for p in people:
        by_name.setdefault(p[1], []).append(p)
    names = sorted(by_name)
    cand: dict[str, list[dict]] = {}
    for i in range(0, len(names), 150):
        vals = " ".join(json.dumps(n, ensure_ascii=False) + "@ko" for n in names[i:i + 150])
        q = f"""SELECT ?item ?n ?b ?d ?img ?title WHERE {{ VALUES ?n {{ {vals} }}
                ?item rdfs:label ?n; wdt:P31 wd:Q5.
                OPTIONAL {{ ?item wdt:P569 ?b }} OPTIONAL {{ ?item wdt:P570 ?d }} OPTIONAL {{ ?item wdt:P18 ?img }}
                OPTIONAL {{ ?art schema:about ?item; schema:isPartOf <https://ko.wikipedia.org/>; schema:name ?title }} }}"""
        for b in sparql(q):
            qid = b["item"]["value"].rsplit("/", 1)[1]
            lst = cand.setdefault(b["n"]["value"], [])
            it = next((x for x in lst if x["qid"] == qid), None)
            if not it:
                it = {"qid": qid, "b": set(), "d": set(), "img": None, "title": None}
                lst.append(it)
            for k in ("b", "d"):
                if k in b and year(b[k]["value"]) is not None:
                    it[k].add(year(b[k]["value"]))
            if "img" in b:
                it["img"] = urllib.parse.unquote(b["img"]["value"].rsplit("/", 1)[1])
            if "title" in b:
                it["title"] = b["title"]["value"]
        print(f"  위키데이터 {min(i + 150, len(names))}/{len(names)}", flush=True)
        time.sleep(1)
    matched: dict[str, dict] = {}
    for name, plist in by_name.items():
        cs = cand.get(name, [])
        for pid, ko, hj, born, died, c in plist:
            def ok(x, v):
                return v is not None and any(abs(y - v) <= 1 for y in x)
            both = [x for x in cs if ok(x["b"], born) and ok(x["d"], died)]
            one = [x for x in cs if ok(x["b"], born) or ok(x["d"], died)]
            pick = both if both else one
            if len(pick) == 1:
                x = pick[0]
                matched[pid] = {"qid": x["qid"], "title": x["title"], "img": x["img"],
                                "match": "생몰년" if both else ("생년" if ok(x["b"], born) else "몰년")}
    print("  이음", len(matched), "명", flush=True)
    # 위키백과 요약
    for n, (pid, m) in enumerate(matched.items()):
        if not m["title"]:
            continue
        r = get_json("https://ko.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(m["title"].replace(" ", "_")))
        if r and r.get("type") == "standard":
            m["summary"] = r.get("extract", "")
            m["url"] = r.get("content_urls", {}).get("desktop", {}).get("page")
        if n % 200 == 0:
            print(f"  위키백과 {n}/{len(matched)}", flush=True)
        time.sleep(0.25)
    # 공용 그림 정보
    imgs = sorted({m["img"] for m in matched.values() if m.get("img")})
    info: dict[str, dict] = {}
    for i in range(0, len(imgs), 40):
        titles = "|".join("File:" + t for t in imgs[i:i + 40])
        r = get_json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "titles": titles, "prop": "imageinfo", "iiprop": "url|extmetadata",
            "iiurlwidth": 320, "format": "json"}))
        for pg in (r or {}).get("query", {}).get("pages", {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            md = ii.get("extmetadata", {})
            info[pg["title"].removeprefix("File:")] = {
                "thumb": ii.get("thumburl"), "page": ii.get("descriptionurl"),
                "license": strip_html(md.get("LicenseShortName", {}).get("value", "")),
                "artist": strip_html(md.get("Artist", {}).get("value", ""))[:80],
                "desc": strip_html(md.get("ImageDescription", {}).get("value", ""))[:120]}
        time.sleep(1)
    for m in matched.values():
        f = m.pop("img", None)
        if f and info.get(f, {}).get("thumb"):
            m["img"] = info[f]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"_note": "위키데이터(CC0)·한국어 위키백과 요약(CC BY-SA 4.0)·위키미디어 공용 그림 정보. "
                                        "국편 인물과 이름+생몰년(±1)으로 이은 것만. 이 앱 해설이 아님.",
                               "persons": matched}, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"people": len(people), "matched": len(matched),
            "summary": sum(1 for m in matched.values() if m.get("summary")),
            "image": sum(1 for m in matched.values() if m.get("img"))}


if __name__ == "__main__":
    print(build(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5000))
