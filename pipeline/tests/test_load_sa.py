"""한국사료총서 일기: 한자 숫자, 날 나누기."""
from sillok.load_sa import cn_num, nice_title, split_days


def test_cn_num():
    assert [cn_num(x) for x in ("初一", "初十", "十", "十五", "二十", "二十三", "廿三", "三十", "正")] == \
        [1, 10, 10, 15, 20, 23, 23, 30, 1]


def test_split_days_forward_only():
    text = "七月初一日 是日晴 去念八 初二日 朝食後 十五日 不是新日 初三日 在山中 八月初一日 雨"
    parts = list(split_days("x", "[七月]", text, 1592, 7, False))
    days = [(p[2].month, p[2].day) for p in parts]
    # 初三日은 十五日 뒤라 날 표시로 보지 않는다(앞으로만). 八月初一日은 다음 달로 넘어감
    assert days == [(7, 1), (7, 2), (7, 15), (8, 1)]
    assert parts[0][0] == "x_d01" and parts[-1][0] == "x_d01m08"


def test_nice_title():
    assert nice_title("[七月] 初二日", "初二日 朝食後 衙屬") == "[七月] 初二日 · 朝食後 衙屬"
    assert nice_title("統制使를 遞差하자는 啓", "...") == "統制使를 遞差하자는 啓"


def test_diary_day_markers():
    from sillok.load_sa import split_days, cn_num
    assert cn_num("卄三") == 23
    text = "一日 晴\n二日 雨 留二日而去\n卄日 風\n晦日 雪"
    got = [(a.day) for _i, _t, a, _b, _s in split_days("x", "", text, 1593, 4, False)]
    from hdate import lunar
    assert got == [1, 2, 20, lunar.month_length(1593, 4)]  # 본문 속 "留二日"은 날 표시가 아니다


def test_fix_years_by_ganji():
    from types import SimpleNamespace
    from hdate import ganji, lunar
    from sillok.load_sa import fix_years_by_ganji
    items = []
    for d in range(1, 11):  # 실제는 1704년인데 간지 해 甲申을 1644로 짚은 경우
        gz = ganji.name(ganji.day_index(lunar.lunar_to_jdn(1704, 1, d)), hanja=True)
        items.append((f"b_0010_0020_d{d:02d}", "", SimpleNamespace(year=1644, month=1, day=d, leap=False, day_ganji=None),
                      f"初{d}日{gz} 晴", []))
    assert {a.year for _i, _t, a, _b, _s in fix_years_by_ganji(items)} == {1704}
