"""같은 기사의 요약 두 벌을 원문과 나란히 놓는 비교 문서 (모델 비교용).

사용: python3 -m sillok.compare <db> <A.jsonl> <B.jsonl> <출력.md> [--names A B]
B에 있는 기사만 싣는다. 국편 국문 제목은 싣지 않는다.
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


def render(db: str, a_path: str, b_path: str, names=("A", "B")) -> str:
    con = sqlite3.connect(db)
    a, b = _load(a_path), _load(b_path)
    out = [f"# 요약 비교: {names[0]} vs {names[1]}", "", f"기사 {len(b)}건", ""]
    for aid in b:
        text = con.execute("SELECT text FROM article WHERE id=?", (aid,)).fetchone()[0]
        out += [f"## [{aid}]({SILLOK_URL.format(id=aid)}) · {len(text)}자", "",
                "<details><summary>원문</summary>", "", text.replace("\n", "  \n"), "", "</details>", "",
                f"### {names[0]}", "", *_render_one(a.get(aid)), "", f"### {names[1]}", "", *_render_one(b[aid]), ""]
    return "\n".join(out)


if __name__ == "__main__":
    args = sys.argv[1:]
    names = ("A", "B")
    if "--names" in args:
        i = args.index("--names")
        names = (args[i + 1], args[i + 2])
        del args[i:i + 3]
    db, a, b, out = args
    open(out, "w", encoding="utf-8").write(render(db, a, b, names))
    print(out)
