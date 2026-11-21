"""실록 기사 날짜를 hdate로 JDN 변환하고, 기사 머리 일진과 계산 일진을 대조한다."""
from __future__ import annotations

import sys
from collections import Counter

from hdate import ganji, lunar_to_jdn

from .parse import iter_files, parse_file


def check(directory: str, books=None):
    stats = Counter()
    bad = []
    for f in iter_files(directory, books):
        for a in parse_file(f):
            stats["articles"] += 1
            if a.year is None:
                stats["no_date"] += 1
                continue
            if a.day is None:
                stats["no_day"] += 1
                continue
            try:
                j = lunar_to_jdn(a.year, a.month, a.day, a.leap)
            except ValueError as e:
                bad.append((a.id, "date", str(e)))
                continue
            if a.day_ganji is None:
                stats["no_ganji"] += 1
                continue
            calc = ganji.name(ganji.day_index(j), hanja=True)
            if calc == a.day_ganji:
                stats["ganji_ok"] += 1
            else:
                bad.append((a.id, "ganji", f"기사 {a.day_ganji} / 계산 {calc}"))
    return stats, bad


if __name__ == "__main__":
    st, bad = check(sys.argv[1], tuple(sys.argv[2:]) or None)
    print(dict(st), "불일치", len(bad))
    for b in bad[:50]:
        print(*b)
