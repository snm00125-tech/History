"""요약 JSONL 검증·적재.

한 줄 = 기사 하나:
{"id": "wna_12504013_001",
 "title": "왜군이 쳐들어와 부산·동래가 함락되다",          # 25자 이하
 "sentences": [{"text": "…", "evidence": ["倭寇至", "翌日陷東萊府"]}, …],   # 1~max_sentences(원문 길이)개
 "commentary": [{"text": "…"}]}                          # 선택. 원문 밖 배경 설명(해설)

규칙 (CLAUDE.md 4): 요약 문장은 원문에 있는 사실만. 문장마다 근거 구절(원문 그대로의 한문 인용)을
하나 이상 단다. 인용이 원문에 글자 그대로 없으면 거부한다. 위치(문자 오프셋)는 여기서 계산해 저장한다.
해설은 원문 밖 지식이므로 verified=0(검수 전)으로 저장한다.
국편 국문 제목(ref_title_ko)은 요약 입력이 아니다. 여기서는 베끼지 않았는지 대조하는 데만 쓴다.

사용: python3 -m sillok.summary <db> <jsonl> [--author 이름] [--check]   # --check: 검사만, DB에 안 씀
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS summary (
  article_id TEXT PRIMARY KEY REFERENCES article(id),
  title TEXT NOT NULL,
  sentences TEXT NOT NULL,       -- JSON [{text, evidence:[{start,end,quote}]}]
  commentary TEXT,               -- JSON [{text, verified}] 또는 NULL
  author TEXT NOT NULL,          -- 만든 주체 (예: pilot-session, API 모델 ID)
  review_status TEXT NOT NULL DEFAULT 'draft',  -- draft | approved | rejected
  source_file TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summary_evidence (
  article_id TEXT NOT NULL REFERENCES article(id),
  sent INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL, quote TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS summary_evidence_article ON summary_evidence(article_id);
"""
TITLE_MAX = 25


def max_sentences(text_len: int) -> int:
    """요약 문장 상한: 원문 250자당 1문장, 최소 3, 최대 10 (사용자 결정: 내용이 많으면 더 써도 됨)."""
    return min(10, max(3, -(-text_len // 250)))
# 한글 음절·자모. U+318D(ㆍ)는 원문에서 가운뎃점으로 쓰이므로 뺀다.
_HANGUL = re.compile("[\uac00-\ud7a3\u3131-\u318c\u318e]")


class SummaryError(ValueError):
    pass


@dataclass
class Checked:
    id: str
    title: str
    sentences: list[dict]
    commentary: list[dict] | None


def _norm(s: str) -> str:
    return re.sub(r"[\s·,.!?'\"“”‘’()]", "", s)


def check(rec: dict, text: str, ref_title: str | None = None) -> Checked:
    aid = rec.get("id")
    title = (rec.get("title") or "").strip()
    if not title:
        raise SummaryError(f"{aid}: 제목 없음")
    if len(title) > TITLE_MAX:
        raise SummaryError(f"{aid}: 제목 {len(title)}자 > {TITLE_MAX}")
    if ref_title and _norm(ref_title) and _norm(title) == _norm(ref_title):
        raise SummaryError(f"{aid}: 제목이 국편 국문 제목과 같음 (번역문 사용 금지)")
    sents = rec.get("sentences") or []
    limit = max_sentences(len(text))
    if not 1 <= len(sents) <= limit:
        raise SummaryError(f"{aid}: 요약 문장 {len(sents)}개 (1~{limit})")
    out = []
    for i, s in enumerate(sents):
        st = (s.get("text") or "").strip()
        if not st:
            raise SummaryError(f"{aid}: {i}번 문장 비어 있음")
        ev = s.get("evidence") or []
        if not ev:
            raise SummaryError(f"{aid}: {i}번 문장에 근거 구절 없음")
        evs = []
        for q in ev:
            if len(q) < 2:
                raise SummaryError(f"{aid}: 근거 구절이 너무 짧음: {q!r}")
            if _HANGUL.search(q):
                raise SummaryError(f"{aid}: 근거 구절에 한글이 있음(원문 인용이 아님): {q!r}")
            pos = text.find(q)
            if pos < 0:
                raise SummaryError(f"{aid}: 근거 구절이 원문에 없음: {q!r}")
            evs.append({"start": pos, "end": pos + len(q), "quote": q})
        out.append({"text": st, "evidence": evs})
    com = rec.get("commentary")
    if com:
        com = [{"text": c["text"].strip(), "verified": False} for c in com if c.get("text", "").strip()]
    return Checked(aid, title, out, com or None)


def load_jsonl(db: str, path: str, author: str, check_only: bool = False) -> tuple[int, list[str]]:
    """check_only=True면 DB에 쓰지 않고 검사만 한다(여러 작업자가 동시에 돌려도 안전)."""
    if check_only:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    else:
        con = sqlite3.connect(db)
        con.executescript(SCHEMA)
    ok, errors = 0, []
    with con:
        for ln, line in enumerate(open(path, encoding="utf-8"), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{path}:{ln}: JSON 오류 {e}")
                continue
            row = con.execute("SELECT text FROM article WHERE id=?", (rec.get("id"),)).fetchone()
            if row is None:
                errors.append(f"{path}:{ln}: 없는 기사 ID {rec.get('id')}")
                continue
            ref = con.execute("SELECT title FROM ref_title_ko WHERE article_id=?", (rec["id"],)).fetchone()
            try:
                c = check(rec, row[0], ref[0] if ref else None)
            except SummaryError as e:
                errors.append(f"{path}:{ln}: {e}")
                continue
            if check_only:
                ok += 1
                continue
            con.execute("DELETE FROM summary_evidence WHERE article_id=?", (c.id,))
            con.execute("INSERT OR REPLACE INTO summary VALUES (?,?,?,?,?, 'draft', ?)",
                        (c.id, c.title, json.dumps(c.sentences, ensure_ascii=False),
                         json.dumps(c.commentary, ensure_ascii=False) if c.commentary else None,
                         author, path))
            con.executemany("INSERT INTO summary_evidence VALUES (?,?,?,?,?)",
                            [(c.id, i, e["start"], e["end"], e["quote"])
                             for i, s in enumerate(c.sentences) for e in s["evidence"]])
            ok += 1
    con.close()
    return ok, errors


if __name__ == "__main__":
    args = sys.argv[1:]
    author = "pilot-session"
    if "--author" in args:
        i = args.index("--author")
        author = args[i + 1]
        del args[i:i + 2]
    check_only = "--check" in args
    if check_only:
        args.remove("--check")
    n, errs = load_jsonl(args[0], args[1], author, check_only)
    print(f"{'통과' if check_only else '적재'} {n}건, 오류 {len(errs)}건")
    for e in errs:
        print(" ", e)
    sys.exit(1 if errs else 0)
