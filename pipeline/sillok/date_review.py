"""날짜 검수 규칙 적용 (적재 뒤에 돈다). 규칙으로 판정할 수 있는 것만 확정하고, 나머지는 사람 검수로 남긴다.

    python3 -m sillok.date_review data/work.sqlite

article.review_rule 에 판정을 적는다(확정이면 needs_review=0):
  month_shift      일진 조정: 그 달(실록 한 권의 한 달)의 날짜 기사 절반 이상이 같은 날수만큼 밀림 → 음력 표와 실록의 달 경계 차이. 조정 날짜 확정.
  month_edge       일진 조정: 그 달의 앞쪽 또는 뒤쪽 날들만 같은 날수만큼 밀림(가운데는 맞음) → 29/30일 달 길이 차이. 확정.
  month_all_dated  일진 조정: 그 달에 일진이 맞는 날이 하나도 없고 모두 같은 차이 → 확정.
  ganji_typo       일진 불일치(차이 3일 이상): 그 달의 다른 날들은 표와 맞음 → 머리 일진 오기로 보고 표 날짜 확정.
  ganji_month_error 일진 불일치: 한 달 내내 같은 큰 차이(예: 고종 1874·1875·1893년 20~25일) → 원자료 간지 칸 오류. 표 날짜 확정.
  isolated         일진 조정: 한 달 가운데 하루만 1~2일 어긋남 → 일진 오기인지 날짜 오기인지 규칙으로 못 가림. 사람 검수(needs_review 유지).
  no_such_day      표에 없는 날(예: 29일까지인 달의 30일) → 그 달 단위(month)로 배치. 사람 검수 유지.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict

from hdate import lunar_to_jdn
from hdate.lunar import month_length

SAME_MONTH = "book=? AND lunar_year=? AND lunar_month=? AND lunar_leap=?"


def apply(db: str) -> dict:
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(article)")]
    if "review_rule" not in cols:
        con.execute("ALTER TABLE article ADD COLUMN review_rule TEXT")
    stats: dict[str, int] = defaultdict(int)
    with con:
        con.execute("UPDATE article SET review_rule=NULL WHERE review_rule IS NOT NULL")
        # 일진 조정
        adj = defaultdict(list)
        for aid, b, y, m, lp, d, dl in con.execute(
                "SELECT id, book, lunar_year, lunar_month, lunar_leap, lunar_day, ganji_delta FROM article "
                "WHERE jdn_status='ganji_adjusted'"):
            adj[(b, y, m, lp)].append((aid, d, dl))
        for k, lst in adj.items():
            dated = con.execute(f"SELECT COUNT(*) FROM article WHERE {SAME_MONTH} AND day_ganji_src IS NOT NULL "
                                "AND jdn_status IN ('ok','ganji_adjusted','ganji_conflict')", k).fetchone()[0]
            ok_days = [d for (d,) in con.execute(
                f"SELECT DISTINCT lunar_day FROM article WHERE {SAME_MONTH} AND jdn_status='ok'", k)]
            from collections import Counter
            main_delta, main_n = Counter(dl for _, _, dl in lst).most_common(1)[0]
            main = [x for x in lst if x[2] == main_delta]
            days = {d for _, d, _ in main}
            if len(main) >= 5 and len(main) / max(dated, 1) >= 0.5:
                rule = "month_shift"
            elif ok_days and (min(days) > max(ok_days) or max(days) < min(ok_days)):
                rule = "month_edge"
            elif not ok_days:
                rule = "month_all_dated"
            else:
                rule = "isolated"
            for aid, _, dl in lst:
                r = rule if dl == main_delta else "isolated"  # 그 달 주된 차이와 다른 것은 따로 본다
                con.execute("UPDATE article SET review_rule=?, needs_review=? WHERE id=?",
                            (r, int(r == "isolated"), aid))
                stats[r] += 1
        # 일진 불일치
        conf = defaultdict(list)
        for aid, b, y, m, lp, dl in con.execute(
                "SELECT id, book, lunar_year, lunar_month, lunar_leap, ganji_delta FROM article "
                "WHERE jdn_status='ganji_conflict'").fetchall():
            conf[(b, y, m, lp)].append((aid, dl))
        for k, lst in conf.items():
            ok = con.execute(f"SELECT COUNT(*) FROM article WHERE {SAME_MONTH} AND jdn_status='ok'", k).fetchone()[0]
            deltas = {dl for _, dl in lst}
            if ok:
                rule = "ganji_typo"            # 그 달 다른 날은 표와 맞음 → 이 날 머리 일진 오기
            elif len(lst) >= 5 and len(deltas) <= 2:
                rule = "ganji_month_error"     # 한 달 내내 같은 큰 차이 → 원자료 간지 칸이 통째로 틀림, 표 날짜 유지
            else:
                rule = "isolated"
            for aid, _ in lst:
                con.execute("UPDATE article SET review_rule=?, needs_review=? WHERE id=?", (rule, int(rule == "isolated"), aid))
                stats[rule if rule != "isolated" else "conflict_unsure"] += 1
        # 표에 없는 날 → 그 달 단위로
        for aid, y, m, lp in con.execute(
                "SELECT id, lunar_year, lunar_month, lunar_leap FROM article WHERE jdn_status='invalid_date' "
                "AND lunar_year IS NOT NULL AND lunar_month IS NOT NULL").fetchall():
            try:
                start = lunar_to_jdn(y, m, 1, bool(lp))
                end = start + month_length(y, m, bool(lp)) - 1
            except ValueError:
                continue
            con.execute("UPDATE article SET review_rule='no_such_day', date_precision='month', jdn_start=?, jdn_end=? "
                        "WHERE id=?", (start, end, aid))
            stats["no_such_day"] += 1
    left = con.execute("SELECT COUNT(*) FROM article WHERE needs_review=1").fetchone()[0]
    return {**stats, "needs_review_left": left}


if __name__ == "__main__":
    print(apply(sys.argv[1]))
