"""같은 기사의 요약 여러 벌을 원문과 나란히 놓는 비교 문서 (모델 비교용).

사용: python3 -m sillok.compare <db> <A.jsonl> <B.jsonl> [<C.jsonl> ...] <출력.md> [--names A B C ...]
마지막 파일(기준)에 있는 기사만 싣는다. 국편 국문 제목은 싣지 않는다.
"""
from __future__ import annotations

import json
import sqlite3
import sys

from .parse import SILLOK_URL


def _load(path: str) -> dict:
    out = {}
    for ln in open(path, encoding="utf-8"):
        if ln.strip():
            r = json.loads(ln)
            out[r["id"]] = r
    return out


def _render_one(r: dict | None) -> list[str]:
    if r is None:
        return ["(없음)"]
    lines = [f"**{r['title']}**", ""]
    for i, s in enumerate(r["sentences"], 1):
        lines.append(f"{i}. {s['text']}  \n   근거: " + " · ".join(f"`{q}`" for q in s["evidence"]))
    for c in r.get("commentary") or []:
        lines.append(f"> 해설: {c['text']}")
    return lines


def render(db: str, paths: list[str], names: list[str] | None = None) -> str:
    con = sqlite3.connect(db)
    sets = [_load(p) for p in paths]
    names = list(names or [chr(65 + i) for i in range(len(paths))])
    if len(names) != len(paths):
        raise SystemExit("--names 개수가 파일 개수와 다름")
    base = sets[-1]
    out = [f"# 요약 비교: {' vs '.join(names)}", "", f"기사 {len(base)}건", ""]
    for aid in base:
        text = con.execute("SELECT text FROM article WHERE id=?", (aid,)).fetchone()[0]
        out += [f"## [{aid}]({SILLOK_URL.format(id=aid)}) · {len(text)}자", "",
                "<details><summary>원문</summary>", "", text.replace("\n", "  \n"), "", "</details>", ""]
        for name, s in zip(names, sets):
            out += [f"### {name}", "", *_render_one(s.get(aid)), ""]
    return "\n".join(out)


if __name__ == "__main__":
    args = sys.argv[1:]
    names = None
    if "--names" in args:
        i = args.index("--names")
        names = args[i + 1:]
        del args[i:]
    db, *paths, out = args
    if len(paths) < 2:
        raise SystemExit("비교할 파일이 2개 이상 필요")
    open(out, "w", encoding="utf-8").write(render(db, paths, names))
    print(out)
