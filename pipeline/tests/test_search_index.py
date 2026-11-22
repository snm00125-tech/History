"""제목 검색 색인: 두 글자, 흔한 두 글자 제외, 차분 부호화."""
import json

from sillok import search_index as si


def test_build_and_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "STOP_DF", 3)
    docs = [("이순신이 왜적을 격파하다", "1592-08-14", "a1", "wna"),
            ("왜적이 쳐들어오다", "1592-05-23", "a2", "wna"),
            ("이순신 전사", "1598-12-16", "a3", "wnb"),
            ("왜적 소식", "1593-01-01", "a4", "wna")]
    st = si.build(docs, tmp_path)
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert st["docs"] == 4 and "왜적" in meta["stop"]  # 3번 나와 흔한 말로 빠짐
    shard = json.loads((tmp_path / "i" / f"{si.shard_of('순신')}.json").read_text())
    enc = shard["순신"]
    ids, p = [], 0
    for d in enc:
        p += d
        ids.append(p)
    assert ids == [0, 2]
    assert si.bigrams("이 순신") == {"이순", "순신"}
