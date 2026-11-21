"""generate: API 없이 prepare → (가짜 결과) collect → retry 흐름 점검."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace as N

import pytest

from sillok import generate
from sillok.prompt import system_prompt, user_message

DB = Path(__file__).parents[1] / "data" / "work.sqlite"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="작업 DB 없음")


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "w.sqlite"
    db.write_bytes(DB.read_bytes())
    monkeypatch.setattr(generate, "ROOT", tmp_path)
    (tmp_path / "summaries").mkdir()
    return db


def _msg(text, stop="end_turn"):
    return N(model=generate.MODEL, stop_reason=stop, content=[N(type="text", text=text)],
             usage=N(input_tokens=1000, output_tokens=500, cache_read_input_tokens=2000,
                     cache_creation_input_tokens=0))


class FakeClient:
    def __init__(self, answers):
        self.answers = answers
        self.messages = N(batches=N(retrieve=lambda _id: N(processing_status="ended", request_counts=None),
                                    results=lambda _id: [N(custom_id=k, result=N(type="succeeded", message=v))
                                                         for k, v in self.answers.items()]))


def test_prompt_stable_and_no_ref_title():
    con = sqlite3.connect(DB)
    s = system_prompt(con)
    assert s == system_prompt(con)
    refs = [t for (t,) in con.execute("SELECT title FROM ref_title_ko WHERE article_id LIKE 'wn_1250401%'")]
    assert not any(t in s for t in refs)
    assert "上'은 선조" in user_message(con, "wna_12505001_001")


def test_flow(env, monkeypatch):
    generate.main(["prepare", str(env), "t1", "--years", "1592", "1592", "--months", "5", "--limit", "3"])
    d = env.parent / "data" / "gen" / "t1"
    reqs = [json.loads(x) for x in open(d / "round1.requests.jsonl")]
    assert len(reqs) == 3 and reqs[0]["params"]["model"] == "claude-opus-5-5"
    con = sqlite3.connect(env)
    texts = {q["custom_id"]: con.execute("SELECT text FROM article WHERE id=?", (q["article_id"],)).fetchone()[0]
             for q in reqs}
    a, b, c = list(texts)
    good = lambda k: json.dumps({"title": "시험 제목", "commentary": [],
                                 "sentences": [{"text": "시험 문장.", "evidence": [texts[k][1:4]]}]},
                                ensure_ascii=False)
    bad = json.dumps({"title": "시험", "commentary": [],
                      "sentences": [{"text": "x", "evidence": ["原文無此句也"]}]}, ensure_ascii=False)
    monkeypatch.setattr(generate, "_client", lambda: FakeClient(
        {a: _msg(good(a)), b: _msg(bad), c: _msg("", stop="refusal")}))
    generate.main(["collect", str(env), "t1"])
    st = json.loads((d / "state.json").read_text())
    assert st["rounds"][0]["ok"] == 1 and st["rounds"][0]["failed"] == 2 and st["rounds"][0]["usd"] > 0
    assert con.execute("SELECT COUNT(*) FROM summary WHERE author='claude-opus-5-5'").fetchone()[0] == 1
    generate.main(["retry", str(env), "t1"])
    r2 = [json.loads(x) for x in open(d / "round2.requests.jsonl")]
    assert len(r2) == 1  # 거절(refusal)은 사람 검토로
    assert r2[0]["params"]["messages"][-1]["content"].startswith("자동 검사에서 거부")
    # 이미 요약된 기사는 다시 고르지 않는다
    assert a.replace("Q", "?") not in generate.select(con, [1592, 1592], [5], ["wna", "wnb"], None)
