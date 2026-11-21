import json
import sqlite3

import pytest

from sillok.summary import SummaryError, check, load_jsonl

TEXT = "○十三日壬寅,倭寇至。 翌日陷東萊府, 府使宋象賢死之。 從事朴箎ㆍ尹暹皆死"


def rec(**kw):
    r = {"id": "x", "title": "왜군이 쳐들어오다",
         "sentences": [{"text": "왜군이 쳐들어왔다.", "evidence": ["倭寇至"]}]}
    r.update(kw)
    return r


def test_offsets():
    c = check(rec(sentences=[{"text": "동래부가 함락되었다.", "evidence": ["陷東萊府", "府使宋象賢死之"]}]), TEXT)
    ev = c.sentences[0]["evidence"]
    assert [TEXT[e["start"]:e["end"]] for e in ev] == ["陷東萊府", "府使宋象賢死之"]
    assert check(rec(sentences=[{"text": "죽었다.", "evidence": ["朴箎ㆍ尹暹"]}]), TEXT)  # ㆍ는 한글 아님


@pytest.mark.parametrize("bad", [
    rec(sentences=[{"text": "없는 사실.", "evidence": ["倭寇大至"]}]),        # 원문에 없는 인용
    rec(sentences=[{"text": "근거 없음.", "evidence": []}]),                   # 근거 없음
    rec(sentences=[{"text": "번역 인용.", "evidence": ["왜구가 이르다"]}]),     # 한글 인용
    rec(sentences=[]),                                                          # 문장 없음
    rec(sentences=[{"text": "a", "evidence": ["倭寇至"]}] * 4),                # 짧은 기사 3문장 초과
    rec(title="가" * 26),                                                       # 제목 길이
])
def test_reject(bad):
    with pytest.raises(SummaryError):
        check(bad, TEXT)


def test_reject_ref_title():
    with pytest.raises(SummaryError):
        check(rec(title="왜군이 쳐들어오다"), TEXT, ref_title="왜군이 쳐들어 오다")


def test_load(tmp_path):
    db = tmp_path / "t.sqlite"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE article(id TEXT PRIMARY KEY, text TEXT);"
                      "CREATE TABLE ref_title_ko(article_id TEXT, title TEXT);")
    con.execute("INSERT INTO article VALUES ('a1', ?)", (TEXT,))
    con.commit()
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        rec(id="a1"), rec(id="nope"), {**rec(id="a1"), "sentences": [{"text": "x", "evidence": ["없음x"]}]},
    ]), encoding="utf-8")
    n, errs = load_jsonl(str(db), str(f), "test")
    assert n == 1 and len(errs) == 2
    assert con.execute("SELECT COUNT(*) FROM summary_evidence").fetchone()[0] == 1


def test_max_sentences():
    from sillok.summary import max_sentences
    assert [max_sentences(n) for n in (10, 750, 751, 1004, 2500, 11143)] == [3, 3, 4, 5, 10, 10]
