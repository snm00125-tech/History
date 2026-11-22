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
