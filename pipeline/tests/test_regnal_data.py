"""왕력 표를 실록 원문과 대조한다 (원자료가 있을 때만)."""
import re
from pathlib import Path

import pytest

from hdate.regnal import JOSEON, reign, to_lunar_year

RAW = Path(__file__).parents[1] / "data" / "raw" / "sillok_15053647" / "x"
pytestmark = pytest.mark.skipif(not RAW.exists(), reason="원자료 없음")


def _year_heads(book):
    """연도 파일 머리의 (서기, 재위연도 표기)."""
    out = []
    for f in sorted(RAW.glob(f"2nd_{book}_1*.xml")):
        head = f.read_text(encoding="utf-8")[:4000]
        y = re.search(r'<dateOccured date="(\d+)" type="서기"/>', head)
        r = re.search(r'<dateOccured type="재위연도">(\S+) (\S+)</dateOccured>', head)
        if y and r:
            out.append((int(y.group(1)), r.group(1), r.group(2)))
    return out


@pytest.mark.parametrize("r", [r for r in JOSEON if r.book], ids=lambda r: r.king)
def test_year_labels(r):
    heads = _year_heads(r.book)
    assert heads
    for year, king, label in heads:
        assert reign(king) is r
        n = 0 if label == "즉위" else int(label)
        assert to_lunar_year(king, n) == year
    has_jeugwi = any(lbl == "즉위" for _, _, lbl in heads)
    assert has_jeugwi == (r.has_accession_year_label and not r.accession_year_is_first)
