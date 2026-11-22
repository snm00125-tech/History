"""원문 색인: 정규화, varint, 흔한 두 글자 제외."""
import base64
import json

from sillok import fulltext_index as ft


def _decode(b64):
    out, x, shift, prev, res = base64.b64decode(b64), 0, 0, 0, []
    for byte in out:
        x |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            prev += x
            res.append(prev)
            x, shift = 0, 0
    return res


def test_build(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "CUT", 3)
    texts = ["○上曰: 李舜臣破賊。", "上曰, 可。", "龜船之制, 李舜臣所創", "上曰 不允"]
    st = ft.build(texts, tmp_path)
    assert st["docs"] == 4
    shard = json.loads((tmp_path / f"{ft.shard_of('舜臣')}.json").read_text())
    assert _decode(shard["舜臣"]) == [0, 2]
    # 上曰은 3번 나와 빠진다
    sh2 = tmp_path / f"{ft.shard_of('上曰')}.json"
    assert not sh2.exists() or "上曰" not in json.loads(sh2.read_text())
    assert ft.varint([300]) == bytes([0xAC, 0x02])
