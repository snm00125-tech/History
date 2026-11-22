"""원문(한문) 본문 검색 색인 (정적 사이트용). export.py가 부른다.

출력 (out/f/):
  meta.json   {"docs": N, "shards": S, "cut": 흔한 두 글자 기준}
  <n>.json    두 글자 → 문서 번호 목록(차분 + varint → base64). n = crc32(두 글자) % S

- 정규화: 글자(L*)·숫자(N*)만 남긴다(구두점·공백·괄호 제거). 화면 쪽(lib/fulltext.ts)도 같은 규칙.
- 문서 번호 = 제목 검색(s/d)과 같은 번호(날짜순). 결과 확인은 그 문서의 달 파일(m/YYYY-MM.json) 원문으로 한다.
- 흔한 두 글자(문서 CUT개 이상, 예: 上曰)는 빼고, 질의에 그런 두 글자만 있으면 찾지 못한다.
- 메모리를 아끼려고 조각을 PASSES번에 나눠 만든다.
"""
from __future__ import annotations

import base64
import json
import unicodedata
import zlib
from collections import Counter
from pathlib import Path

SHARDS = 4096
CUT = 1000
PASSES = 8


def make_table(texts) -> dict:
    chars: set[str] = set()
    for t in texts:
        chars.update(t)
    return str.maketrans({c: None for c in chars if unicodedata.category(c)[0] not in "LN"})


def norm(s: str, table) -> str:
    return s.translate(table).lower()


def bigram_set(n: str) -> set[str]:
    return {n[i:i + 2] for i in range(len(n) - 1)}


def shard_of(bg: str) -> int:
    return zlib.crc32(bg.encode("utf-8")) % SHARDS


def varint(nums) -> bytes:
    out = bytearray()
    for x in nums:
        while x >= 0x80:
            out.append((x & 0x7F) | 0x80)
            x >>= 7
        out.append(x)
    return bytes(out)


def build(texts: list[str], out: Path) -> dict:
    """texts[i] = 문서 i의 원문(제목 검색 문서 번호와 같은 순서)."""
    out.mkdir(parents=True, exist_ok=True)
    table = make_table(texts)
    normed = [norm(t, table) for t in texts]
    df: Counter = Counter()
    for n in normed:
        df.update(bigram_set(n))
    kept = {bg for bg, c in df.items() if c < CUT}
    total = 0
    for p in range(PASSES):
        post: dict[str, list[int]] = {}
        for i, n in enumerate(normed):
            for bg in bigram_set(n):
                if bg in kept and shard_of(bg) % PASSES == p:
                    post.setdefault(bg, []).append(i)
        shards: dict[int, dict[str, str]] = {}
        for bg, lst in post.items():
            prev, deltas = 0, []
            for x in lst:
                deltas.append(x - prev)
                prev = x
            shards.setdefault(shard_of(bg), {})[bg] = base64.b64encode(varint(deltas)).decode("ascii")
            total += len(lst)
        for n_, m in shards.items():
            (out / f"{n_}.json").write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({"docs": len(texts), "shards": SHARDS, "cut": CUT}), encoding="utf-8")
    return {"docs": len(texts), "bigrams_kept": len(kept), "dropped": len(df) - len(kept), "postings": total}
