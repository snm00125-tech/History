"""세션 안에서(서브에이전트가) 요약을 쓰기 위한 작업 분할·검사·병합.

API 일괄 생성(sillok/generate.py) 대신 Claude Code 세션 사용량으로 요약을 만드는 경로.
지침·검증은 같다: sillok/prompt.py의 RULES와 sillok/summary.py의 check.

    python3 -m sillok.session_gen plan   data/work.sqlite --years 1592 1598     # 묶음 파일 만들기
    python3 -m sillok.session_gen verify data/work.sqlite <묶음>                 # 빠짐·검증 확인 (DB에 안 씀)
    python3 -m sillok.session_gen merge  data/work.sqlite <묶음> [<묶음> ...]    # 통과한 묶음을 DB에 적재
    python3 -m sillok.session_gen todo   data/work.sqlite                       # 남은 묶음 목록

묶음 입력: data/gen/session/<묶음>.md (git 제외, 원문 포함)
묶음 출력: summaries/s_<묶음>.jsonl (git에 넣음)
국편 국문 제목은 입력 파일에 넣지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .prompt import user_message
from .summary import load_jsonl

ROOT = Path(__file__).parents[1]
IN_DIR = ROOT / "data" / "gen" / "session"
OUT_DIR = ROOT / "summaries"
AUTHOR = "session-agent"


def out_path(chunk: str) -> Path:
    return OUT_DIR / f"s_{chunk}.jsonl"


def _chunk_ids(chunk: str) -> list[str]:
    return [ln[4:].strip() for ln in (IN_DIR / f"{chunk}.md").read_text(encoding="utf-8").splitlines()
            if ln.startswith("### ")]


def plan(con, y0: int, y1: int, max_articles: int, max_chars: int) -> list[tuple[str, int, int]]:
    """요약 없는 기사를 연·월(윤달 포함) 순으로 묶는다. 한 달이 크면 a, b, …로 나눈다."""
    IN_DIR.mkdir(parents=True, exist_ok=True)
    rows = con.execute(
        """SELECT id, lunar_year, lunar_month, lunar_leap, length(text) FROM article
           WHERE lunar_year BETWEEN ? AND ? AND id NOT IN (SELECT article_id FROM summary)
           ORDER BY lunar_year, lunar_month, lunar_leap, book, id""", (y0, y1)).fetchall()
    months: dict[tuple, list] = {}
    for aid, y, m, lp, n in rows:
        months.setdefault((y, m, lp), []).append((aid, n))
    out = []
    for (y, m, lp), arts in months.items():
        parts, cur, size = [], [], 0
        for aid, n in arts:
            if cur and (len(cur) >= max_articles or size + n > max_chars):
                parts.append(cur)
                cur, size = [], 0
            cur.append(aid)
            size += n
        parts.append(cur)
        for k, ids in enumerate(parts):
            name = f"{y}_{'L' if lp else ''}{m:02d}" + (f"_{chr(97 + k)}" if len(parts) > 1 else "")
            body = [f"# 요약 묶음 {name} ({len(ids)}건)", ""]
            for aid in ids:
                body += [f"### {aid}", user_message(con, aid), ""]
            (IN_DIR / f"{name}.md").write_text("\n".join(body), encoding="utf-8")
            chars = sum(con.execute("SELECT length(text) FROM article WHERE id=?", (i,)).fetchone()[0] for i in ids)
            out.append((name, len(ids), chars))
    return out


def verify(db: str, chunk: str) -> tuple[bool, list[str]]:
    want = _chunk_ids(chunk)
    p = out_path(chunk)
    if not p.exists():
        return False, [f"출력 없음: {p.relative_to(ROOT)}"]
    got = [json.loads(ln)["id"] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    errs = []
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    dup = sorted({i for i in got if got.count(i) > 1})
    if missing:
        errs.append(f"빠진 기사 {len(missing)}건: {', '.join(missing[:10])}")
    if extra:
        errs.append(f"묶음에 없는 기사: {', '.join(extra[:10])}")
    if dup:
        errs.append(f"중복: {', '.join(dup[:10])}")
    n, check_errs = load_jsonl(db, str(p), AUTHOR, check_only=True)
    errs += check_errs
    return not errs, errs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sillok.session_gen")
    ap.add_argument("cmd", choices=["plan", "verify", "merge", "todo"])
    ap.add_argument("db")
    ap.add_argument("chunks", nargs="*")
    ap.add_argument("--years", nargs=2, type=int, default=[1592, 1598])
    ap.add_argument("--max-articles", type=int, default=90)
    ap.add_argument("--max-chars", type=int, default=25000)
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        con = sqlite3.connect(a.db)
        res = plan(con, *a.years, a.max_articles, a.max_chars)
        for name, n, chars in res:
            print(f"{name}\t{n}건\t{chars}자")
        print(f"묶음 {len(res)}개, 기사 {sum(r[1] for r in res)}건")
    elif a.cmd == "verify":
        bad = 0
        for c in a.chunks:
            ok, errs = verify(a.db, c)
            print(f"{c}: {'통과' if ok else '오류'}")
            for e in errs[:30]:
                print("  ", e)
            bad += not ok
        raise SystemExit(1 if bad else 0)
    elif a.cmd == "merge":
        for c in a.chunks:
            ok, errs = verify(a.db, c)
            if not ok:
                raise SystemExit(f"{c}: 검사 실패, 적재 안 함 ({len(errs)}개 오류)")
            n, errs = load_jsonl(a.db, str(out_path(c)), AUTHOR)
            print(f"{c}: 적재 {n}건")
    elif a.cmd == "todo":
        for f in sorted(IN_DIR.glob("*.md")):
            c = f.stem
            state = "완료" if out_path(c).exists() and verify(a.db, c)[0] else "남음"
            print(f"{c}\t{state}")


if __name__ == "__main__":
    main()
