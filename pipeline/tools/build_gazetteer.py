"""지명 → 좌표 사전(geo/places.json) 만들기. 좌표 출처는 위키데이터(CC0), 추측하지 않는다.

    python3 tools/build_gazetteer.py data/work.sqlite [상위 N=3000]

1. 실록·고려사 원문 국편 지명 색인(span index:지명)에서 많이 나온 지명 N개.
2. 위키데이터 한국(남·북) 장소의 한자 이름(zh/ja 표기)과 바로 맞춘다(data/geo/kr_places.json, 없으면 내려받음).
3. 못 맞춘 것은 한자를 한글로 읽어(data/geo/hanja_reading.json: 국편 역사지리·인물 이름의 한자↔한글 짝에서 만든 글자 읽기표)
   위키데이터 한국어 이름·별칭(+시·군·읍·도·섬 등)으로 찾는다(나라 제한 없음: 대마도·요동·북경 등).
4. 나라 이름(倭·唐·明·日本 …)은 점이 아니라 「나라」로 따로 둔다.
5. 후보가 여럿이면 장소 종류(행정구역 > 궁궐·건물 > 자연) 순으로 고르고 cands에 후보 수를 남긴다.
결과의 모든 좌표는 verified=false (검수 전).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parents[1]
GEO = ROOT / "data" / "geo"
OUT = ROOT / "geo" / "places.json"
UA = "HistoryTimelinePersonal/1.0 (personal non-commercial history app)"
SPARQL = "https://query.wikidata.org/sparql"

VAR = str.maketrans({"尙": "尚", "淸": "清", "靑": "青", "晉": "晋", "黃": "黄", "鄕": "郷", "德": "徳", "廣": "広",
                     "濟": "済", "國": "国", "龍": "竜", "萊": "莱", "營": "営", "縣": "県"})
SUF_HJ = ("郡", "市", "縣", "県", "邑", "面", "區", "区", "洞", "里", "府", "牧", "鎭", "鎮")
SUF_KO = ("", "시", "군", "구", "읍", "면", "도", "섬", "산", "성", "궁", "강", "현", "부", "진")
STATES = set("倭 唐 宋 明 淸 漢 周 遼 金 元 胡 虜 隋 秦 晉 魏 吳 蜀 夏 商 殷 楚 齊 燕 趙 越".split()) | {
    "野人", "兀良哈", "兀狄哈", "日本", "中國", "大明", "高麗", "朝鮮", "倭人", "倭賊", "倭奴", "唐人", "胡人", "日本國",
    "朝鮮國", "琉球", "琉球國", "女眞", "女直", "蒙古", "契丹", "大淸", "皇明", "天朝", "上國", "中朝", "百濟", "新羅",
    "高句麗", "渤海", "西洋", "俄羅斯", "英國", "法國", "美國", "淸國", "大韓", "韓國", "東國", "我國", "本國"}
# 도(道): 짧게 쓴 이름·옛 이름 → 위키데이터 한국어 이름
PROVINCES = {"京畿": "경기도", "平安": "평안도", "平安道": "평안도", "慶尙": "경상도", "慶尙道": "경상도",
             "全羅": "전라도", "全羅道": "전라도", "忠淸": "충청도", "忠淸道": "충청도", "黃海": "황해도",
             "黃海道": "황해도", "江原": "강원도", "江原道": "강원도", "咸鏡": "함경도", "咸鏡道": "함경도",
             "咸吉道": "함경도", "永安道": "함경도", "京畿道": "경기도"}  # 함길도·영안도 = 함경도의 옛 이름
# 위키데이터의 조선 8도 항목에 좌표가 없으면 지금의 남·북도 좌표 가운데로
PROVINCE_PARTS = {"평안도": ["평안남도", "평안북도"], "경상도": ["경상북도", "경상남도"], "전라도": ["전북특별자치도", "전라남도"],
                  "충청도": ["충청북도", "충청남도"], "함경도": ["함경남도", "함경북도"], "황해도": ["황해남도", "황해북도"]}
PALACES = ("창덕궁 ", "경복궁 ", "창경궁 ", "경희궁 ", "덕수궁 ")
# 같은 한글 이름이 여럿인 외국 지명: 지금 쓰는 한국어 이름으로 찾는다
OVERRIDE = {"對馬島": "쓰시마섬", "對馬州": "쓰시마섬", "對馬": "쓰시마섬", "北京": "베이징", "南京": "난징",
            "遼東": "랴오둥반도", "瀋陽": "선양시", "瀋": "선양시", "山海關": "산하이관", "燕京": "베이징",
            "鳳凰城": "펑청시", "長崎": "나가사키시", "江戶": "도쿄", "大坂": "오사카시"}
KOREA_BOX = (33.0, 43.6, 124.0, 131.9)
EAST_ASIA_BOX = (15.0, 60.0, 70.0, 150.0)


def in_box(pt, box) -> bool:
    return pt is not None and box[0] <= pt[0] <= box[1] and box[2] <= pt[1] <= box[3]


# 장소 종류 이름에 이 말이 있으면 우선(앞일수록 높음)
CLASS_PRIORITY = ["도 (행정", "광역시", "특별시", "시 (", "군 (", "구 (", "도시", "군", "시", "구", "읍", "면", "행정",
                  "역사적", "궁", "전각", "건축물", "성", "관아", "섬", "산", "강", "하천", "반도", "고개"]


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).translate(VAR)


def sparql(q: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": q}).encode()
    for i in range(5):
        try:
            req = urllib.request.Request(SPARQL, data=data, headers={
                "User-Agent": UA, "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:  # 429·시간초과 → 쉬었다가
            print("  SPARQL 재시도", i + 1, e, flush=True)
            time.sleep(10 * (i + 1))
    raise SystemExit("SPARQL 실패")


def point(wkt: str) -> tuple[float, float] | None:
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", wkt)
    return (round(float(m[2]), 5), round(float(m[1]), 5)) if m else None


def load_kr_places() -> dict:
    p = GEO / "kr_places.json"
    if not p.exists():
        q = """SELECT ?item ?ko ?zh ?coord ?cls WHERE { VALUES ?country { wd:Q884 wd:Q423 }
               ?item wdt:P17 ?country; wdt:P625 ?coord. ?item rdfs:label ?ko FILTER(LANG(?ko)="ko")
               OPTIONAL { ?item rdfs:label ?zh FILTER(LANG(?zh) IN ("zh-hant","zh","ja")) }
               OPTIONAL { ?item wdt:P31 ?cls } }"""
        GEO.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"results": {"bindings": sparql(q)}}, ensure_ascii=False), encoding="utf-8")
    items: dict[str, dict] = {}
    for b in json.loads(p.read_text(encoding="utf-8"))["results"]["bindings"]:
        q = b["item"]["value"].rsplit("/", 1)[1]
        it = items.setdefault(q, {"ko": b["ko"]["value"], "zh": set(), "cls": set(), "pt": point(b["coord"]["value"])})
        if "zh" in b:
            it["zh"].add(b["zh"]["value"])
        if "cls" in b:
            it["cls"].add(b["cls"]["value"].rsplit("/", 1)[1])
    return items


def reader():
    rd = json.loads((GEO / "hanja_reading.json").read_text(encoding="utf-8"))

    def read(s: str) -> str | None:
        out = []
        for i, ch in enumerate(s):
            r = (rd["first"] if i == 0 else rd["rest"]).get(ch) or rd["rest"].get(ch) or rd["first"].get(ch)
            if not r:
                return None
            out.append(r)
        return "".join(out)
    return read


def class_labels(qids: set[str]) -> dict[str, str]:
    out = {}
    qs = sorted(qids)
    for i in range(0, len(qs), 400):
        vals = " ".join(f"wd:{q}" for q in qs[i:i + 400])
        for b in sparql(f"""SELECT ?c ?l WHERE {{ VALUES ?c {{ {vals} }} ?c rdfs:label ?l FILTER(LANG(?l)="ko") }}"""):
            out[b["c"]["value"].rsplit("/", 1)[1]] = b["l"]["value"]
    return out


def score(cls_names: list[str]) -> int:
    best = len(CLASS_PRIORITY)
    for n in cls_names:
        for i, k in enumerate(CLASS_PRIORITY):
            if k in n:
                best = min(best, i)
    return best


def build(db: str, top: int = 3000) -> dict:
    con = sqlite3.connect(db)
    names = con.execute("""SELECT substr(a.text, s.start+1, s.end-s.start) n, COUNT(*) c FROM span s
                           JOIN article a ON a.id = s.article_id WHERE s.kind='index:지명'
                           GROUP BY n ORDER BY c DESC LIMIT ?""", (top,)).fetchall()
    items = load_kr_places()
    idx: dict[str, set[str]] = defaultdict(set)
    for q, it in items.items():
        for z in it["zh"]:
            z = norm(z)
            idx[z].add(q)
            for s in SUF_HJ:
                if z.endswith(s) and len(z) > len(s) + 1:
                    idx[z[:-len(s)]].add(q)
    read = reader()
    result, todo = {}, []
    for n, c in names:
        if n in STATES or (n.endswith("國") and len(n) <= 4):
            result[n] = {"h": n, "n": c, "kind": "state"}
            continue
        if len(n) == 1:  # 한 글자 지명은 너무 모호하다
            result[n] = {"h": n, "n": c, "kind": "unknown"}
            continue
        if n in PROVINCES or n in OVERRIDE:
            todo.append((n, c))
            continue
        k = norm(n)
        cand = idx.get(k) or (idx.get(k[:-1]) if k[-1] in "道縣郡府牧" and len(k) > 2 else None)
        if cand:
            result[n] = {"h": n, "n": c, "kind": "place", "how": "hanja", "cands": sorted(cand)}
        else:
            todo.append((n, c))
    # 한글 읽기로 위키데이터 이름·별칭 찾기
    want: dict[str, list[str]] = defaultdict(list)  # 한글 후보 이름 → 한자 지명들
    for n, c in todo:
        if n in PROVINCES or n in OVERRIDE:
            want[PROVINCES.get(n) or OVERRIDE[n]].append(n)
            for part in PROVINCE_PARTS.get(PROVINCES.get(n, ""), []):
                want[part].append(n)
            continue
        r = read(n)
        if not r:
            continue
        base = r[:-1] if n[-1] in "道縣郡府牧" and len(n) > 2 else r
        for s in SUF_KO:
            want[base + s].append(n)
        if n[-1] in "殿堂閣樓門亭臺軒齋宮":  # 궁궐 건물
            for pal in PALACES:
                want[pal + r].append(n)
        if n[-1] == "道":  # 평안도 = 평안도(조선) 그대로도
            want[r].append(n)
    found: dict[str, list[tuple[str, tuple, set]]] = defaultdict(list)
    labels = sorted(want)
    for i in range(0, len(labels), 300):
        vals = " ".join(json.dumps(x, ensure_ascii=False) + "@ko" for x in labels[i:i + 300])
        q = f"""SELECT ?item ?l ?coord ?cls WHERE {{ VALUES ?l {{ {vals} }}
                {{ ?item rdfs:label ?l }} UNION {{ ?item skos:altLabel ?l }}
                ?item wdt:P625 ?coord. OPTIONAL {{ ?item wdt:P31 ?cls }} }}"""
        for b in sparql(q):
            qid = b["item"]["value"].rsplit("/", 1)[1]
            it = items.setdefault(qid, {"ko": b["l"]["value"], "zh": set(), "cls": set(), "pt": point(b["coord"]["value"])})
            if "cls" in b:
                it["cls"].add(b["cls"]["value"].rsplit("/", 1)[1])
            for n in want[b["l"]["value"]]:
                found[n].append(qid)
        print(f"  한글 이름 찾기 {min(i + 300, len(labels))}/{len(labels)}", flush=True)
    for n, c in todo:
        if found.get(n):
            how = "province" if n in PROVINCES else "override" if n in OVERRIDE else "reading"
            result[n] = {"h": n, "n": c, "kind": "place", "how": how, "cands": sorted(set(found[n]))}
        else:
            result[n] = {"h": n, "n": c, "kind": "unknown", "ko": read(n)}
    # 후보 고르기
    cls_q = {cl for r in result.values() for q in r.get("cands", []) for cl in items[q]["cls"]}
    cl_names = class_labels(cls_q)
    out = []
    for n, c in names:
        r = result[n]
        if r["kind"] == "place":
            cands = [q for q in r["cands"] if in_box(items[q]["pt"], EAST_ASIA_BOX)]
            if not cands:
                r = {"h": n, "n": c, "kind": "unknown", "ko": read(n)}
            else:
                foreign_ok = n in OVERRIDE
                if not foreign_ok and r["how"] == "reading":  # 읽기로 찾은 것은 한반도 안만
                    cands = [q for q in cands if in_box(items[q]["pt"], KOREA_BOX)]
            if r["kind"] == "place" and n in PROVINCES:
                main = PROVINCES[n]
                exact = [q for q in cands if items[q]["ko"] == main]
                parts = [q for q in cands if items[q]["ko"] in PROVINCE_PARTS.get(main, [])]
                if not exact and parts:  # 남·북도 가운데
                    pts = [items[q]["pt"] for q in parts]
                    qq = "+".join(sorted(parts))
                    items[qq] = {"ko": main, "zh": set(), "cls": set(),
                                 "pt": (round(sum(p[0] for p in pts) / len(pts), 4), round(sum(p[1] for p in pts) / len(pts), 4))}
                    cands = [qq]
                elif exact:
                    cands = exact
            if r["kind"] == "place" and not cands:
                r = {"h": n, "n": c, "kind": "unknown", "ko": read(n)}
            elif r["kind"] == "place":
                cands.sort(key=lambda q: (not foreign_ok and not in_box(items[q]["pt"], KOREA_BOX),
                                          score([cl_names.get(x, "") for x in items[q]["cls"]]), q))
                q = cands[0]
                it = items[q]
                r = {"h": n, "n": c, "kind": "place", "ko": it["ko"], "lat": it["pt"][0], "lon": it["pt"][1],
                     "qid": q, "type": ", ".join(sorted(cl_names.get(x, x) for x in it["cls"]))[:60],
                     "how": r["how"], "cands": len(cands), "verified": False}
                if n in PROVINCES:
                    r["kind"] = "province"
        elif r["kind"] == "state":
            r["ko"] = read(n)
        out.append(r)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"_note": "좌표 출처 위키데이터(CC0). 지명 언급 수 n은 실록·고려사 국편 지명 색인 기준. "
                                        "verified=false: 같은 이름 다른 곳일 수 있음(cands = 후보 수).",
                               "places": out}, ensure_ascii=False, indent=0), encoding="utf-8")
    tot = sum(c for _, c in names)
    st = Counter(r["kind"] for r in out)
    cov = {k: round(sum(r["n"] for r in out if r["kind"] == k) / tot * 100, 1) for k in st}
    return {"names": len(out), "kinds": dict(st), "mention_share_%": cov,
            "ambiguous": sum(1 for r in out if r.get("cands", 1) > 1)}


if __name__ == "__main__":
    print(build(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3000))
