"""요약 생성 지침과 출력 스키마.

시스템 지침은 모든 요청에서 바이트 단위로 같아야 캐시가 맞는다. 날짜·기사별 값은 넣지 않는다.
예시는 파일럿(summaries/pilot_1592_04.jsonl)에서 고정 ID로 골라 원문과 함께 싣는다.
국편 국문 제목(ref_title_ko)은 어디에도 넣지 않는다 (CLAUDE.md 규칙 3).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from hdate import describe

from .summary import TITLE_MAX, max_sentences

PROMPT_VERSION = "v2"  # v2: 해설 추측 금지, 문장 속 사실마다 근거
BOOK_INFO = {
    "wna": ("선조실록", "선조"),
    "wnb": ("선조수정실록", "선조"),
}
EXAMPLE_IDS = ("wna_12504017_004", "wna_12504028_003", "wnb_12504014_015")
PILOT = Path(__file__).parents[1] / "summaries" / "pilot_1592_04.jsonl"

RULES = f"""당신은 조선왕조실록 원문(한문) 기사를 한국어로 요약하는 편찬자다. 결과는 한국사 타임라인 웹 서비스에 그대로 실린다.

## 가장 중요한 원칙: 정확성
- 요약에는 **이 기사 원문에 적힌 사실만** 쓴다. 원문에 없는 사실·추측·배경·평가를 넣지 않는다.
- 문장마다 그 내용의 근거가 되는 원문 구절을 evidence에 단다. 구절은 원문에서 **한 글자도 바꾸지 않고 연속으로 복사**한다(띄어쓰기·문장부호 포함). 원문에 없는 구절, 고쳐 쓴 구절, 한글이 섞인 구절은 자동 검사에서 거부된다.
- 근거 구절은 2자 이상, 너무 길지 않게(대개 4~30자) 문장의 핵심 사실을 직접 뒷받침하는 부분만 고른다. 한 문장에 사실이 여럿이면 구절도 여럿 단다. 문장에 쓴 사실은 모두 근거 구절로 뒷받침되어야 한다.
- 실록 편찬자의 평가·논평(史臣曰, 사론, 인물평)은 사실처럼 쓰지 말고 "실록은 ~라고 평했다/적었다"처럼 출처를 밝힌다.
- 소문·참언·이상한 현상 이야기는 "~라고 한다", "~라고 적었다"로 전한다.
- 원문의 원주(【】 안)도 원문이다. 쓸 때는 필요하면 "원주에 ~라고 적혀 있다"로 밝힌다.
- 교감 표시 (誤字)〔正字〕가 있으면 〔〕 안의 바로잡은 글자를 따른다.
- 다른 기관의 번역문을 떠올려 옮기지 말고, 원문을 직접 읽고 새로 쓴다.

## 해설(commentary)
- 원문 밖 지식(인물의 다른 이름, 관직·제도·용어 뜻, 천문 용어 등)은 요약이 아니라 commentary에 쓴다.
- 확실한 것만, 짧게 쓴다. 독자 이해에 꼭 필요할 때만 넣고, 필요 없으면 빈 배열로 둔다.
- "~로 보인다", "~인 듯하다" 같은 추정은 해설에도 쓰지 않는다. 앞뒤 기사로 미루어 짐작한 내용(이 기사에 이름이 없는 사람을 누구라고 단정하는 것 등)도 쓰지 않는다. 확신이 없으면 해설을 빼라.
- 처음 나오는 어려운 용어(예: 去邠, 加資)는 해설로 짧게 풀어 주면 좋다.
- 해설은 사람이 따로 검수한다.

## 형식
- title: 타임라인에 한 줄로 보이는 제목. {TITLE_MAX}자 이하. 기사의 핵심 사건을 담는다. "~하다" 꼴을 주로 쓴다.
- sentences: 1문장 이상, 요청마다 주어지는 상한 이하. 짧은 기사는 1~2문장이면 충분하다. 내용이 많으면 상한까지 써도 된다. 문장 수보다 정확성과 빠짐없는 핵심 사실이 중요하다.
- 문체: 과거형 평서문("~했다", "~였다"). 한 문장은 너무 길지 않게.
- 인명·지명·관직은 원문 한자를 한국 한자음으로 읽어 적는다(예: 李舜臣 → 이순신, 都元帥 → 도원수). 외국인 이름도 원문 표기를 그대로 한자음으로 읽고, 다른 이름은 해설에 적는다.
- '上'은 그 실록의 국왕이다(요청에 왕 이름이 주어진다). 요약에서는 왕 이름으로 쓴다.
- 날짜: 기사 머리 날짜가 '월 단위'로 주어진 기사(수정실록 등)는 그 날짜를 사건 날짜로 쓰지 않는다. 본문에 날짜(예: 二十七日)가 있으면 그 날짜를 쓴다.
- 출력은 주어진 JSON 스키마를 따른다. JSON 밖에 다른 글을 쓰지 않는다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "evidence"],
                "additionalProperties": False,
            },
        },
        "commentary": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "sentences", "commentary"],
    "additionalProperties": False,
}


def article_header(con: sqlite3.Connection, aid: str) -> tuple[str, str]:
    """→ (요청 머리, 원문)."""
    book, day, jdn, prec, j0, text = con.execute(
        "SELECT book, lunar_day, jdn, date_precision, jdn_start, text FROM article WHERE id=?", (aid,)
    ).fetchone()
    name, king = BOOK_INFO.get(book, (book, "국왕"))
    if prec == "month" and j0 is not None:
        d = describe(j0)
        when = (f"{d.regnal} {'윤' if d.lunar.leap else ''}{d.lunar.month}월 (월 단위: 원자료의 {day or '?'}일은 "
                f"사건 날짜가 아니다)")
    elif jdn is not None:
        d = describe(jdn)
        when = f"{d.regnal} {'윤' if d.lunar.leap else ''}{d.lunar.month}월 {d.lunar.day}일 ({d.day_ganji}일)"
    else:
        when = "날짜 미상"
    head = (f"기사 ID: {aid}\n실록: {name} (이 실록의 '上'은 {king})\n기사 날짜: {when}\n"
            f"요약 문장 상한: {max_sentences(len(text))}")
    return head, text


def user_message(con: sqlite3.Connection, aid: str) -> str:
    head, text = article_header(con, aid)
    return f"{head}\n\n원문:\n{text}"


def system_prompt(con: sqlite3.Connection) -> str:
    """규칙 + 고정 예시. 같은 DB·파일럿이면 항상 같은 문자열."""
    pilot = {}
    for line in PILOT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            pilot[r["id"]] = r
    parts = [RULES, "", "## 예시 (형식과 근거 구절 고르는 법을 참고만 하라)"]
    for i, aid in enumerate(EXAMPLE_IDS, 1):
        r = pilot[aid]
        out = {"title": r["title"],
               "sentences": [{"text": s["text"], "evidence": s["evidence"]} for s in r["sentences"]],
               "commentary": [{"text": c["text"]} for c in r.get("commentary") or []]}
        parts += [f"### 예시 {i}", "입력:", user_message(con, aid), "", "출력:",
                  json.dumps(out, ensure_ascii=False)]
    return "\n".join(parts)
