"""국조보감(國朝寶鑑, 한국고전번역원 고전원문 공공데이터 15141442) → 작업 DB. book = 'gjbg'.

    python3 -m sillok.load_itkc data/raw/itkc_15141442/x data/work.sqlite

원자료: ITKC_GO_1295A_NNNN.xml (한글 태그). <레벨2> 권 > <레벨3> 왕조(中宗朝二) > <레벨4> 해([甲戌九年]).
- 기사 = 레벨4 본문을 ○로 나눈 한 항목. ID = 레벨4 id + '_NNN'(항목 번호, 1부터). 레벨4 id로 ITKC 원문에 닿는다.
- 해: 레벨4 제목의 재위년(王朝 이름의 왕) → hdate.regnal.to_lunar_year. 제목 간지와 대조해 안 맞거나
  재위년으로 못 구하면(정종 '즉위년' 등) 간지로 정한다.
- 달: 항목 머리의 「春正月」「二月」「閏月」. 달 표시가 없는 항목은 앞 항목의 달을 잇는다(해 첫머리 앞은 '그해').
  달 뒤에 일진(「秋七月丙申」)·「朔」이 있으면 그날(day), 항목 머리가 일진뿐이면(「○丙午。」) 그달 안의 그날.
  일진이 그달 안에 없으면 달 단위로 두고 'ganji_not_in_month'(검수).
- 국문 제목이 없다 → 본문 첫 30자를 제목으로(한문, ref_title_ko).
- 원주 → span '원주', 난외주 → span '교감주'(ref = 고친 글자), 외자(imghj) → 〓 + span 'newchar'.
- 서문·전문·제신 성명·총서·범례·발문(레벨3이 '朝'·'代理'가 아닌 것)은 싣지 않는다.
- 각 왕 첫 레벨4([中宗朝], 왕의 행장 요약)는 날짜 없음(none).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from hdate import ganji, lunar
from hdate.regnal import reign, to_lunar_year
from .load import SCHEMA
from .load_kh import date_fields
from .load_sa import BOOK_SCHEMA
from .load_sjw import make_title
from .parse import NEWCHAR_MARK, Span, _join_surrogates

BOOK = "gjbg"
BOOK_NAME = "국조보감"

KING_KO = {"太祖": "태조", "定宗": "정종", "太宗": "태종", "世宗": "세종", "文宗": "문종", "端宗": "단종", "世祖": "세조",
           "睿宗": "예종", "成宗": "성종", "中宗": "중종", "仁宗": "인종", "明宗": "명종", "宣祖": "선조", "仁祖": "인조",
           "孝宗": "효종", "顯宗": "현종", "肅宗": "숙종", "景宗": "경종", "英祖": "영조", "正祖": "정조", "純祖": "순조",
           "憲宗": "헌종", "哲宗": "철종",
           "純宗": "순조", "文祖": "순조"}  # 文祖代理 = 효명세자 대리청정(순조 27~30년). 제목의 純宗 = 순조의 옛 묘호

_GZ = "[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]"
_NUM = "[〇一二三四五六七八九十百]+"
_DIGIT = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
# 레벨4 제목: [甲戌九年] [壬申卽位年] [純宗二十七年丁亥]
_TITLE = re.compile(rf"^\[(?:({_GZ})({_NUM}|元|卽位|即位)年|([一-龥]{{2}})({_NUM}|元)年({_GZ}))\]$")
# 항목 머리의 해 표시: 壬申元年 / 庚辰二年。 / 文宗大王二年壬申
_YEAR_HEAD = re.compile(rf"^(?:{_GZ})?(?:[一-龥]{{1,3}}?大王)?(?:{_NUM}|元|卽位|即位)年(?:{_GZ})?[。\s]*")
_MONTH = re.compile(rf"^(?:是年)?([春夏秋冬])?(閏)?(正|十一|十二|十|[一二三四五六七八九])?月(?:[。\s]*)(朔|晦)?[。\s]*({_GZ})?")
_SEASON = re.compile(r"^(?:是年|是歲)?[春夏秋冬][。\s]")
_DAY_ONLY = re.compile(rf"^(朔|晦)?({_GZ})[。\s]")


def nfc(s: str) -> str:
    """호환 한자(U+F900~, 예: 六 U+F9D1)를 통합 한자로. 길이는 그대로라 오프셋이 바뀌지 않는다."""
    return unicodedata.normalize("NFC", s)


def cn_num(s: str) -> int:
    """한자 수 → 정수 (一 ~ 九十九, 元=1)."""
    if s == "元":
        return 1
    if s in ("卽位", "即位"):
        return 0
    if "十" in s:
        a, _, b = s.partition("十")
        return (_DIGIT[a] if a else 1) * 10 + (_DIGIT[b] if b else 0)
    n = 0
    for ch in s:
        n = n * 10 + _DIGIT[ch]
    return n


def parse_title(title: str) -> tuple[str | None, int, str | None] | None:
    """레벨4 제목 → (해 간지, 재위년(0=즉위년), 제목 속 왕 이름|None). 해 제목이 아니면 None."""
    m = _TITLE.match(nfc(title.strip()))
    if not m:
        return None
    if m[1]:
        return m[1], cn_num(m[2]), None
    return m[5], cn_num(m[4]), m[3]


def king_of(chapter: str) -> str | None:
    """레벨3 제목(中宗朝二, 文祖代理一) → 한글 왕 이름. 왕조 장이 아니면 None."""
    m = re.match(r"^([一-龥]{2})(?:朝|代理)", nfc(chapter.strip()))
    return KING_KO.get(m[1]) if m else None


def resolve_year(king: str, ry: int, gz: str | None) -> tuple[int | None, str]:
    """(왕, 재위년, 해 간지) → (음력 연도, 판정). 판정: regnal | ganji_fixed | ganji_only | unknown."""
    try:
        y = to_lunar_year(king, ry)
    except ValueError:
        y = None
    if gz is None:
        return y, ("regnal" if y is not None else "unknown")
    gi = ganji.index_of(gz)
    if y is not None and ganji.year_index(y) == gi:
        return y, "regnal"
    est = y if y is not None else reign(king).first_year - 1 + ry  # 즉위년(ry=0) → 1년 앞
    cands = [c for c in range(est - 30, est + 31) if ganji.year_index(c) == gi]
    best = min(cands, key=lambda c: abs(c - est))
    return best, ("ganji_fixed" if y is not None else "ganji_only")


def day_in_month(y: int, m: int, leap: bool, gz: str) -> int | None:
    """그달에서 일진이 gz인 날(1~30). 없으면 None."""
    try:
        s = lunar.lunar_to_jdn(y, m, 1, leap)
        n = lunar.month_length(y, m, leap)
    except ValueError:
        return None
    off = (ganji.index_of(gz) - ganji.day_index(s)) % 60
    return off + 1 if off < n else None


def parse_head(item: str, cur_month: tuple[int, bool] | None):
    """항목 머리 → (달(월, 윤)|None, 날 표시('朔'|'晦'|간지|None), 머리에 달이 있었나).
    달 표시가 없으면 cur_month를 잇는다."""
    item = nfc(item[:80])
    s = _YEAR_HEAD.sub("", item, count=1) if _YEAR_HEAD.match(item) else item
    m = _MONTH.match(s)
    if m and (m[2] or m[3]):
        if m[3]:
            mo, leap = cn_num(m[3]) if m[3] != "正" else 1, bool(m[2])
        elif cur_month:  # 閏月 = 앞 달의 윤달
            mo, leap = cur_month[0], True
        else:
            return None, None, True
        return (mo, leap), (m[4] or m[5]), True
    if _SEASON.match(s):  # 「春。」처럼 철만: 달 모름
        return None, None, True
    d = _DAY_ONLY.match(s)
    if d and cur_month:
        return cur_month, (d[1] or d[2]), False
    return cur_month, None, False


# ---------- 본문 ----------

class _Builder:
    def __init__(self):
        self.parts, self.n, self.spans, self.pages = [], 0, [], []

    def add(self, s):
        if not s:
            return
        s = re.sub(r"\s*\n\s*", "", s)  # 판면 줄바꿈(<line/>)은 원문에 없는 것: 붙인다
        s = _join_surrogates(s)
        self.parts.append(s)
        self.n += len(s)

    def walk(self, el):
        tag, start = el.tag, self.n
        if tag == "imghj":
            self.add(NEWCHAR_MARK)
            self.spans.append(Span("newchar", start, self.n, el.get("href")))
        elif tag == "페이지":
            self.pages.append((self.n, el.get("number")))
        else:  # 문자효과(격자=빈칸, 반전=해 간지 등)는 글자만 남긴다
            self.add(el.text)
            for ch in el:
                self.walk(ch)
            if tag == "원주" and self.n > start:
                self.spans.append(Span("원주", start, self.n))
            elif tag == "주석" and self.n > start:
                self.spans.append(Span("교감주", start, self.n, el.get("id")))
        self.add(el.tail)

    def text(self):
        return "".join(self.parts)


def body_text(content) -> tuple[str, list[Span], list]:
    b = _Builder()
    for i, p in enumerate(content.findall("단락")):
        if i:
            b.parts.append("\n")
            b.n += 1
        b.add(p.text)
        for ch in p:
            b.walk(ch)
    return b.text(), b.spans, b.pages


def split_items(text: str) -> list[tuple[int, int]]:
    """○로 나눈 항목의 (시작, 끝). 앞뒤 공백·○는 뺀다."""
    out, pos = [], 0
    for seg in text.split("○"):
        a, b = pos, pos + len(seg)
        pos = b + 1
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if b > a:
            out.append((a, b))
    return out


def _parse(path: Path):
    raw = path.read_bytes()
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return ET.fromstring(_join_surrogates(raw.decode("utf-8")))


def iter_files(src: str):
    """→ dict(id, title, y, m, leap, d, gz, f(date_fields), text, spans, reg, src, file) + 통계 키 'year_how'."""
    for path in sorted(Path(src).glob("ITKC_GO_1295A_*.xml")):
        root = _parse(path)
        for l3 in root.iter("레벨3"):
            t3 = l3.find("메타정보/제목정보/제목")
            king = king_of("".join(t3.itertext()) if t3 is not None else "")
            if king is None:
                continue
            for l4 in l3.iter("레벨4"):
                t4 = l4.find("메타정보/제목정보/제목")
                title4 = "".join(t4.itertext()).strip() if t4 is not None else ""
                content = l4.find("본문정보/내용")
                if content is None:
                    continue
                text, spans, pages = body_text(content)
                notes = {x.get("id"): "".join(x.findtext("주석내용") or "").strip()
                         for x in l4.findall("주석정보/주석항목")}
                spans = [Span(s.kind, s.start, s.end, notes.get(s.ref, s.ref)) if s.kind == "교감주" else s
                         for s in spans]
                pt = parse_title(title4)
                y, how, reg = None, "none", None
                if pt:
                    ygz, ry, k2 = pt
                    k = KING_KO.get(k2, king) if k2 else king
                    y, how = resolve_year(k, ry, ygz)
                    reg = f"{k} {'즉위년' if ry == 0 else f'{ry}년'}"
                cur = None
                for i, (a, b) in enumerate(split_items(text), 1):
                    item = text[a:b]
                    ispans = [Span(s.kind, max(s.start, a) - a, min(s.end, b) - a, s.ref)
                              for s in spans if s.start < b and s.end > a]
                    page = next((p for pos, p in reversed(pages) if pos <= a), pages[0][1] if pages else None)
                    m = leap = d = gz = None
                    status_override = None
                    if y is not None:
                        cur, mark, _ = parse_head(item, cur)
                        if cur:
                            m, leap = cur
                            if mark == "朔":
                                d = 1
                            elif mark == "晦":
                                try:
                                    d = lunar.month_length(y, m, leap)
                                except ValueError:
                                    d = None
                            elif mark:
                                gz = mark
                                d = day_in_month(y, m, leap, gz)
                                if d is None:
                                    status_override = "ganji_not_in_month"
                    f = date_fields(y, m, d, bool(leap), None, gz if d is not None else None)
                    if y is not None and m is None:
                        f["status"] = "no_month"
                    if status_override and f["precision"] == "month":
                        f.update(status=status_override, review=1)
                    yield dict(id=f"{l4.get('id')}_{i:03d}", title=make_title(item), y=y, m=m,
                               leap=f["leap"] if m else False, d=d if f["precision"] == "day" else None,
                               gz=gz, f=f, text=item, spans=ispans, reg=reg,
                               src=[l4.get("id"), page], file=path.name, year_how=how)


def load_itkc(src: str, db: str) -> dict:
    con = sqlite3.connect(db)
    con.executescript(SCHEMA + BOOK_SCHEMA)
    stats: dict = {"articles": 0, "year_how": {}}
    with con:
        for t in ("span", "ref_title_ko", "subject", "article_group"):
            con.execute(f"DELETE FROM {t} WHERE article_id IN (SELECT id FROM article WHERE book=?)", (BOOK,))
        con.execute("DELETE FROM article WHERE book=?", (BOOK,))
        con.execute("DELETE FROM book WHERE code=?", (BOOK,))
        rows, titles, spans, seen = [], [], [], set()
        for a in iter_files(src):
            if a["id"] in seen or not a["text"].strip():
                continue
            seen.add(a["id"])
            f = a["f"]
            stats["year_how"][a["year_how"]] = stats["year_how"].get(a["year_how"], 0) + 1
            rows.append((a["id"], BOOK, a["y"], a["m"], int(a["leap"]), a["d"], a["gz"], f["jdn"], f["jdn_table"],
                         f["status"], f["delta"], f["review"], f["precision"], f["start"], f["end"], a["text"], "[]",
                         json.dumps(a["src"], ensure_ascii=False), a["file"], a["reg"]))
            titles.append((a["id"], a["title"]))
            spans += [(a["id"], s.kind, s.start, s.end, s.ref) for s in a["spans"]]
        con.executemany("INSERT INTO article (id,book,lunar_year,lunar_month,lunar_leap,lunar_day,day_ganji_src,"
                        "jdn,jdn_table,jdn_status,ganji_delta,needs_review,date_precision,jdn_start,jdn_end,text,"
                        "subjects,sources,file,regnal_src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.executemany("INSERT INTO ref_title_ko VALUES (?,?)", titles)
        con.executemany("INSERT INTO span VALUES (?,?,?,?,?)", spans)
        con.execute("INSERT INTO book VALUES (?,?,?)", (BOOK, BOOK_NAME, "itkc"))
        stats["articles"] = len(rows)
    con.close()
    return stats


if __name__ == "__main__":
    t = time.perf_counter()
    print(load_itkc(sys.argv[1], sys.argv[2]), f"{time.perf_counter() - t:.1f}s")
