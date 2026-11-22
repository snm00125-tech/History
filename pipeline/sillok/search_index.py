"""제목 검색 색인 (정적 사이트용). export.py가 부른다.

출력 (out/s/):
  meta.json            {"docs": N, "chunk": C, "shards": S, "stop": [흔해서 뺀 두 글자 …]}
  d/<k>.json           문서 덩어리: [[제목, 양력(YYYY-MM-DD 또는 ""), 기사 ID, 책 코드], …]  (번호 k*C ~ )
  i/<n>.json           두 글자 → 문서 번호 목록(차분 부호화). n = 두 글자의 해시 % S

검색: 질의의 두 글자들 중 색인에 있는 것들의 목록을 교집합 → 그 문서들의 제목에 질의가 그대로 들어 있는지 확인.
문서 번호 순서 = 날짜 순서라, 앞 번호부터 보이면 시간순 결과가 된다.
흔한 두 글자(예: '하다')는 목록이 너무 커서 색인에서 뺀다(STOP_DF 이상).
"""
from __future__ import annotations

import json
import zlib
from collections import defaultdict
from pathlib import Path

CHUNK = 2000
SHARDS = 2048
STOP_DF = 15000


def norm(s: str) -> str:
    return "".join(s.split()).lower()


def bigrams(s: str) -> set[str]:
    t = norm(s)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def shard_of(bg: str) -> int:
    return zlib.crc32(bg.encode("utf-8")) % SHARDS


def build(docs: list[tuple[str, str, str, str]], out: Path) -> dict:
    """docs: (제목, 양력, ID, 책) — 날짜 순으로 정렬돼 있어야 한다."""
    (out / "d").mkdir(parents=True, exist_ok=True)
    (out / "i").mkdir(parents=True, exist_ok=True)
    for k in range(0, len(docs), CHUNK):
        (out / "d" / f"{k // CHUNK}.json").write_text(
            json.dumps([list(d) for d in docs[k:k + CHUNK]], ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
    post: dict[str, list[int]] = defaultdict(list)
    for i, d in enumerate(docs):
        for bg in bigrams(d[0]):
            post[bg].append(i)
    stop = sorted(bg for bg, lst in post.items() if len(lst) >= STOP_DF)
    shards: dict[int, dict[str, list[int]]] = defaultdict(dict)
    for bg, lst in post.items():
        if len(lst) >= STOP_DF:
            continue
        prev, enc = 0, []
        for x in lst:
            enc.append(x - prev)
            prev = x
        shards[shard_of(bg)][bg] = enc
    for n, m in shards.items():
        (out / "i" / f"{n}.json").write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":")),
                                            encoding="utf-8")
    meta = {"docs": len(docs), "chunk": CHUNK, "shards": SHARDS, "stop": stop}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"docs": len(docs), "bigrams": len(post), "stop": len(stop), "shard_files": len(shards)}
