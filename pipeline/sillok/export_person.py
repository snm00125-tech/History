"""인물 내보내기 (export.py가 부른다). 인물 표가 없으면 아무것도 하지 않는다.

출력:
  p/<n>.json     인물 조각(n = 번호 // 500): {id: {정보…, "docs": [차분 부호화한 검색 문서 번호], "off": [[양력, 관직, 형태, 문서 번호|-1], …]}}
  pi/<초성>.json 이름 찾기: [[id, 한글명, 한자명, 생년, 몰년, 구분, 언급 수, 첫 해, 끝 해], …] (언급 많은 순)
기사 목록은 검색용 문서 덩어리(s/d/)를 그대로 쓴다(문서 번호 = 날짜순).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

SHARD = 500
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def shard_of(pid: str) -> int:
    return int(pid[2:]) // SHARD


def choseong(s: str) -> str:
    if not s:
        return "etc"
    c = ord(s[0]) - 0xAC00
    return CHO[c // 588] if 0 <= c < 11172 else "etc"


def export_persons(con, out: Path, doc_of: dict[str, int], solar_of) -> dict:
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='article_person'").fetchone():
        return {}
    (out / "p").mkdir(parents=True, exist_ok=True)
    (out / "pi").mkdir(parents=True, exist_ok=True)
    docs: dict[str, list[int]] = defaultdict(list)
    for aid, pid in con.execute("SELECT article_id, person_id FROM article_person"):
        if aid in doc_of:
            docs[pid].append(doc_of[aid])
    offs: dict[str, list] = defaultdict(list)
    for pid, j, y, office, status, aid in con.execute(
            "SELECT person_id, jdn, lunar_year, office, status, article_id FROM person_office ORDER BY person_id, jdn"):
        offs[pid].append([solar_of(j) if j else (str(y) if y else ""), office, status, doc_of.get(aid, -1)])
    shards: dict[int, dict] = defaultdict(dict)
    index: dict[str, list] = defaultdict(list)
    for pid, ko, hj, ja, ho, siho, bon, born, died, kind in con.execute("SELECT * FROM person"):
        ds = sorted(set(docs.get(pid, [])))
        if not ds:
            continue
        prev, enc = 0, []
        for x in ds:
            enc.append(x - prev)
            prev = x
        info = {k: v for k, v in (("ko", ko), ("hj", hj), ("ja", ja), ("ho", ho), ("siho", siho), ("bon", bon),
                                  ("born", born), ("died", died), ("kind", kind)) if v}
        shards[shard_of(pid)][pid] = {**info, "docs": enc, "off": offs.get(pid, [])}
        index[choseong(ko or "")].append([pid, ko, hj, born, died, kind, len(ds), ds[0], ds[-1]])
    for n, m in shards.items():
        (out / "p" / f"{n}.json").write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for c, lst in index.items():
        lst.sort(key=lambda r: -r[6])
        (out / "pi" / f"{c}.json").write_text(json.dumps(lst, ensure_ascii=False, separators=(",", ":")),
                                             encoding="utf-8")
    return {"persons": sum(len(v) for v in index.values()), "shards": len(shards)}
