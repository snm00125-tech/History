"""국조보감(load_itkc)·주한일본공사관기록/한국근대사자료집성(load_jh) 날짜 해석 (원자료 없이)."""
from hdate import lunar
from hdate.calendar import solar_to_jdn
from sillok.load_itkc import (cn_num, day_in_month, king_of, parse_head, parse_title, resolve_year,
                              split_items)
from sillok.load_jh import clean_title, cn_int, parse_attr, parse_date_text, resolve, to_range


# ---------- 국조보감 ----------

def test_cn_num():
    assert [cn_num(s) for s in ("元", "卽位", "九", "十", "十六", "二十六", "四十六", "三十")] == [1, 0, 9, 10, 16, 26, 46, 30]


def test_parse_title():
    assert parse_title("[甲戌九年]") == ("甲戌", 9, None)
    assert parse_title("[壬申卽位年]") == ("壬申", 0, None)
    assert parse_title("[丙戌六年]") == ("丙戌", 6, None)  # 호환 한자 六(U+F9D1)
    assert parse_title("[純宗二十七年丁亥]") == ("丁亥", 27, "純宗")
    assert parse_title("[中宗朝]") is None


def test_king_of():
    assert king_of("中宗朝二") == "중종"
    assert king_of("文祖代理一") == "순조"
    assert king_of("國朝寶鑑序") is None


def test_resolve_year():
    assert resolve_year("중종", 9, "甲戌") == (1514, "regnal")
    # 국조보감은 세조를 유년칭원으로 센다(丙子元年 = 1456). 실록 왕력(즉위년칭원)과 달라 간지로 고친다
    assert resolve_year("세조", 1, "丙子") == (1456, "ganji_fixed")
    # 정종은 실록에 즉위년이 없어 재위년으로 못 구함 → 간지
    assert resolve_year("정종", 0, "戊寅") == (1398, "ganji_only")
    assert resolve_year("단종", 0, "壬申") == (1452, "regnal")


def test_parse_head():
    assert parse_head("秋七月丙申。上卽位于壽昌宮", None) == ((7, False), "丙申", True)
    assert parse_head("元年秋七月丙申。上卽位", None) == ((7, False), "丙申", True)
    assert parse_head("庚辰二年。春正月朔。羣臣請獻壽", None) == ((1, False), "朔", True)
    assert parse_head("文宗大王二年壬申五月丙午。十四日。", None) == ((5, False), "丙午", True)
    assert parse_head("閏月。諭諸道觀察使曰", (2, False)) == ((2, True), None, True)
    assert parse_head("閏三月。命", (2, False)) == ((3, True), None, True)
    assert parse_head("冬十月。擢朴彭年爲副提學", (9, False)) == ((10, False), None, True)
    assert parse_head("是年七月。白嶽山巨巖下墜", (9, False)) == ((7, False), None, True)
    assert parse_head("命兩府六曹臺諫", (7, False)) == ((7, False), None, False)  # 앞 달을 잇는다
    assert parse_head("丙申。祔葬于康陵", (3, False)) == ((3, False), "丙申", False)
    assert parse_head("三年臺諫刑曹請徙", None) == (None, None, False)  # 해 첫머리, 달 없음


def test_day_in_month():
    assert day_in_month(1392, 7, False, "丙申") == 17  # 태조 즉위 1392-07-17(음)
    s = lunar.lunar_to_jdn(1592, 4, 1)
    assert day_in_month(1592, 4, False, "壬寅") == 2302669 - s + 1  # 선조 25년 4월 13일 壬寅
    # 그달에 없는 일진
    n = lunar.month_length(1592, 4)
    assert sum(day_in_month(1592, 4, False, g) is None for g in
               [a + b for a, b in zip("甲乙丙丁戊己庚辛壬癸" * 6, "子丑寅卯辰巳午未申酉戌亥" * 5)]) == 60 - n


def test_split_items():
    t = "元年春正月。甲。○乙。 ○ 丙"
    assert [t[a:b] for a, b in split_items(t)] == ["元年春正月。甲。", "乙。", "丙"]


# ---------- 주한일본공사관기록·한국근대사자료집성 ----------

def test_cn_int():
    assert [cn_int(s) for s in ("二十七", "廿七", "初六", "旬二", "三十", "一○", "５", "四百九十四")] == \
        [27, 27, 6, 12, 30, 10, 5, 494]


def test_parse_date_text_east():
    p = parse_date_text
    assert p("明治二十七年五月十二日") == dict(y=1894, m=5, d=12, cal="solar", leap=False, year_src="era")
    assert p("光武四年五月 日")["y"] == 1900 and p("光武四年五月 日")["d"] is None
    assert p("隆熙二年三月一日")["y"] == 1908
    assert p("大正二年一月二十二日")["y"] == 1913
    r = p("開國五百三年十一月初三日")
    assert (r["y"], r["m"], r["d"], r["cal"]) == (1894, 11, 3, "lunar")
    r = p("甲午九月二十三日", 1894)
    assert (r["y"], r["cal"], r["year_src"]) == (1894, "lunar", "ganji")
    r = p("己酉潤二月初四日 (陽三月二十五日)", 1909)
    assert (r["y"], r["m"], r["d"], r["leap"]) == (1909, 2, 4, True)
    r = p("二十七年六月七日接到", 1894)  # 연호 없는 해 → 明治
    assert (r["y"], r["year_src"]) == (1894, "bare")
    r = p("我曆六月十二日")
    assert (r["y"], r["m"], r["d"], r["cal"]) == (None, 6, 12, "solar")
    assert p("明治四十一年八月十匕日")["d"] is None  # 十匕日: 날을 못 읽는다
    assert p("明治四十年八月一○日")["d"] == 10


def test_parse_date_text_west():
    p = parse_date_text
    r = p("June 7, 1894. 8-10p.m.")
    assert (r["y"], r["m"], r["d"]) == (1894, 6, 7)
    assert (p("15 Janvier 95")["y"], p("15 Janvier 95")["m"]) == (1895, 1)
    assert (p("Fd. 8.20 Feb. 14th, ’96")["y"], p("Fd. 8.20 Feb. 14th, ’96")["d"]) == (1896, 14)
    assert p("le 1/13 Juillet 1894")["d"] == 13  # 율리우스/그레고리 겹표기 → 그레고리력
    assert p("Tokio, 17 Sept. 11.45 a.m.")["y"] is None  # 11은 시각
    assert p("12th August, 11th Year Kwang M")["y"] is None
    assert (p("20/12, 1893 5. 20 p. m.")["m"], p("20/12, 1893 5. 20 p. m.")["d"]) == (12, 20)
    assert p("Le 25eme jour de la 4eme lune de l'année") is None


def test_parse_attr():
    assert parse_attr("1894-05-12") == dict(y=1894, m=5, d=12, lunar=False, leap=False)
    assert parse_attr("9999-02-18")["y"] is None
    assert parse_attr("1894-99-99") == dict(y=1894, m=None, d=None, lunar=False, leap=False)
    assert parse_attr("1909-02-04L1")["leap"] is True
    assert parse_attr("") is None


def test_to_range():
    assert to_range(1894, 2, None, "solar") == ("month", solar_to_jdn(1894, 2, 1), solar_to_jdn(1894, 2, 28), None)
    assert to_range(1894, 2, 30, "solar") is None
    assert to_range(1984, 2, 1, "solar") is None  # 범위 밖
    j = lunar.lunar_to_jdn(1888, 11, 2)
    assert to_range(1888, 11, 2, "lunar") == ("day", j, j, (1888, 11, False, 2))


def test_resolve():
    r = resolve([("dateSend", "1894-05-12", "明治二十七年五月十二日")], None)
    assert (r["y"], r["m"], r["d"], r["status"], r["r"][1]) == (1894, 5, 12, None, solar_to_jdn(1894, 5, 12))
    # 속성 오기(1984) → 표기
    r = resolve([("dateSend", "1984-10-01", "明治二十七年十月一日")], None)
    assert (r["y"], r["status"], r["review"]) == (1894, "date_fixed", 1)
    # 표기에 달·날만: 같은 문서 다른 칸의 해
    r = resolve([("dateSend", None, "我曆五月二十五日"), ("dateReceived", "1894-06-28", "我六月二十八日")], None)
    assert (r["y"], r["m"], r["d"], r["status"]) == (1894, 5, 25, None)
    # 해 미상 → 앞 문서에서 (검수)
    r = resolve([("dateSend", "9999-02-18", "二月十八日")], dict(y=1897, m=1, d=5, cal="solar"))
    assert (r["y"], r["status"], r["review"]) == (1897, "year_inferred", 1)
    # 음력(간지 해) → KASI 표
    r = resolve([("dateSend", "1888-11-02L0", "戊子十一月初二日")], None)
    assert r["cal"] == "lunar" and r["r"][1] == lunar.lunar_to_jdn(1888, 11, 2)
    # 프랑스어 음력 표기는 속성(L)대로 음력
    r = resolve([("dateSend", "1886-04-25L0", "Le 25eme jour de la 4eme lune de l'année")], None)
    assert r["cal"] == "lunar"
    # 프랑스어 양력 표기인데 속성에 L → 양력
    r = resolve([("dateSend", "1895-01-15L0", "15 Janvier 95")], None)
    assert r["cal"] == "solar" and r["r"][1] == solar_to_jdn(1895, 1, 15)
    # 표기의 해가 장 안에 없고 속성의 해가 흔하면 속성 (明治十四年 = 三 빠짐)
    r = resolve([("dateSend", "1901-03-16", "明治十四年三月十六日")], None, support={1901: 10})
    assert (r["y"], r["status"]) == (1901, "date_conflict")
    # 「同 午後二時 接」: 앞 문서와 같은 날
    r = resolve([("dateReceived", "1894-99-99", "同日 午後一時 接")], dict(y=1894, m=7, d=3, cal="solar"))
    assert (r["m"], r["d"], r["status"]) == (7, 3, "same_as_prev")
    assert resolve([("dateSend", "9999-99-99", "fd.")], None) is None


def test_clean_title():
    assert clean_title("(5) 東學黨再燃ノ件") == "東學黨再燃ノ件"
    assert clean_title("(11-1)[東學黨ニ關スル續報] ") == "[東學黨ニ關スル續報]"
    assert clean_title("【20】 유럽4개국 공사로") == "유럽4개국 공사로"
    assert clean_title("1) [上件]") == "[上件]"
