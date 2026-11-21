"""국사편찬위원회 조선왕조실록 원문 XML(공공데이터포털 15053647) → 기사 단위.

파일: 2nd_<실록ID>_<NNN>.xml  (예: 2nd_wna_125.xml = 선조실록 25년)
계층: level1 실록 > level2 연(또는 총서·부록) > level3 월 > level4 일 > level5 기사
- level4/front/date: dateOccured type="서기" date="1592-04-13L0"(L0 평달, L1 윤달, 일 미상은 ??),
  type="간지"(일진, 미상은 □□)
- level5 id = 기사 ID(예: wna_12504013_001). sillok.history.go.kr 원문 링크에 쓴다.
- level5/front/biblioData/title/mainTitle 은 국사편찬위원회가 단 국문 기사 제목이다.
  번역 산물일 수 있어 저장하지 않는다(CLAUDE.md 규칙 3, 사용자 확인 전까지).

본문(text) 규칙
- paragraph는 줄바꿈으로 잇는다.
- index(이름·지명·서명·연호·관직)는 글자 그대로 두고 위치를 spans에 남긴다.
- annotation 원주(【…】)·교감주(〔…〕)·postScript(사론)도 글자 그대로 두고 spans에 종류를 남긴다.
- newChar(유니코드에 없는 외자)는 '〓' 한 글자로 바꾸고 spans에 코드(KC…)를 남긴다.
- 원자료에 이중 이스케이프된 문자 참조(&#x2554F;)가 남아 있어 실제 문자로 푼다.
- 일부 파일은 확장 한자를 UTF-16 대리쌍 참조(&#55381;&#56892;)로 적어 XML 파서가 거부한다. 합쳐서 읽는다.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

NEWCHAR_MARK = "〓"
_CHARREF = re.compile(r"&#x([0-9A-Fa-f]+);|&#(\d+);")
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2}|\?\?)L([01])$")
_FILE = re.compile(r"^2nd_(w[a-z]{2})_(\d{3})\.xml$")

SILLOK_URL = "https://sillok.history.go.kr/id/{id}"


_SURROGATE_REF = re.compile(r"&#(?:x([dD][89abAB][0-9a-fA-F]{2})|(5[56]\d{3}));&#(?:x([dD][c-fC-F][0-9a-fA-F]{2})|(5[67]\d{3}));")


def _join_surrogates(s: str) -> str:
    """UTF-16 대리쌍으로 적힌 문자 참조(&#55381;&#56892;)를 한 문자 참조로 합친다."""
    def f(m):
        hi = int(m.group(1), 16) if m.group(1) else int(m.group(2))
        lo = int(m.group(3), 16) if m.group(3) else int(m.group(4))
        if not (0xD800 <= hi <= 0xDBFF and 0xDC00 <= lo <= 0xDFFF):
            return m.group(0)
        return f"&#x{0x10000 + ((hi - 0xD800) << 10) + (lo - 0xDC00):X};"
    return _SURROGATE_REF.sub(f, s)


def _unescape(s: str) -> str:
    s = _join_surrogates(s)
    return _CHARREF.sub(lambda m: chr(int(m.group(1), 16)) if m.group(1) else chr(int(m.group(2))), s)


@dataclass
class Span:
    kind: str  # index:이름, index:지명, ..., 원주, 교감주, 사론, newchar
    start: int
    end: int
    ref: str | None = None  # 인물 ID(M_…), 외자 코드(KC…) 등


@dataclass
class Article:
    id: str  # wna_12504013_001
    book: str  # wna
    year: int | None  # 음력 연도 (총서·부록은 None)
    month: int | None
    day: int | None  # 일 미상이면 None
    leap: bool
    day_ganji: str | None  # 일진(한자). 미상이면 None
    subjects: list[str]
    sources: list[tuple[str, str]]  # (판본, 쪽)
    text: str
    spans: list[Span] = field(default_factory=list)
    file: str = ""

    @property
    def url(self) -> str:
        return SILLOK_URL.format(id=self.id)


class _TextBuilder:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.n = 0
        self.spans: list[Span] = []

    def add(self, s: str | None, drop_blank: bool = False) -> None:
        if not s or (drop_blank and not s.strip()):
            return
        # XML 정렬용 줄바꿈+들여쓰기는 공백 하나로 (원래 공백이었는지 알 수 없어 낱말 경계만 보존)
        s = _unescape(re.sub(r"\s*\n\s*", " ", s))
        self.parts.append(s)
        self.n += len(s)

    def walk(self, el: ET.Element, in_note: bool = False) -> None:
        """in_note: 부모가 annotation이면 True. 주석 상자 안의 정렬용 공백은 원문에 없으므로 버린다."""
        tag = el.tag
        start = self.n
        if tag == "newChar":
            self.add(NEWCHAR_MARK)
            self.spans.append(Span("newchar", start, self.n, el.get("href")))
        else:
            is_note = tag == "annotation"
            self.add(el.text, drop_blank=is_note)
            for ch in el:
                self.walk(ch, in_note=is_note)
            kind = None
            if tag == "index":
                kind = f"index:{el.get('type')}"
            elif is_note:
                kind = el.get("type") or "annotation"
            elif tag == "postScript":
                kind = "사론"
            if kind and self.n > start:
                self.spans.append(Span(kind, start, self.n, el.get("ref")))
        if tag != "paragraph":
            self.add(el.tail, drop_blank=in_note)

    def text(self) -> str:
        return "".join(self.parts)


def _article_text(text_el: ET.Element | None) -> tuple[str, list[Span]]:
    tb = _TextBuilder()
    if text_el is None:
        return "", []
    paras = text_el.findall("./content/paragraph")
    for i, p in enumerate(paras):
        if i:
            tb.add("\x00")  # 자리표시 후 아래에서 \n으로 (add가 \n을 지우므로)
        tb.walk(p)
    txt = tb.text().replace("\x00", "\n")
    assert len(txt) == tb.n
    return txt, sorted(tb.spans, key=lambda s: (s.start, -s.end))


def _parse_date(front: ET.Element | None):
    """level4 front → (year, month, day|None, leap, ganji|None). 날짜 없으면 None."""
    if front is None:
        return None
    d = front.find("./biblioData/date/dateOccured[@type='서기']")
    if d is None or not d.get("date"):
        return None
    m = _DATE.match(d.get("date"))
    if not m:
        raise ValueError(f"알 수 없는 날짜 형식: {d.get('date')}")
    y, mo, dd, lp = m.groups()
    g = front.find("./biblioData/date/dateOccured[@type='간지']")
    gt = (g.text or "").strip() if g is not None else ""
    ganji = gt if len(gt) == 2 and "□" not in gt else None
    return int(y), int(mo), None if dd == "??" else int(dd), lp == "1", ganji


def _article(el5: ET.Element, book: str, date, fname: str) -> Article:
    bib = el5.find("./front/biblioData")
    subjects = [s.text.strip() for s in bib.findall("subjectClass") if s.text] if bib is not None else []
    sources = []
    if bib is not None:
        for s in bib.findall("source"):
            mt, pg = s.find("mainTitle"), s.find("page")
            sources.append((
                f"{mt.get('type', '')}:{(mt.text or '').strip()}" if mt is not None else "",
                pg.get("begin", "") if pg is not None else "",
            ))
    text, spans = _article_text(el5.find("text"))
    y, mo, d, leap, g = date if date else (None, None, None, False, None)
    return Article(el5.get("id"), book, y, mo, d, leap, g, subjects, sources, text, spans, fname)


def parse_file(path: str | Path) -> Iterator[Article]:
    path = Path(path)
    m = _FILE.match(path.name)
    if not m:
        raise ValueError(f"실록 파일명이 아님: {path.name}")
    book = m.group(1)
    raw = path.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = ET.fromstring(_join_surrogates(raw.decode("utf-8")))

    def rec(el: ET.Element, date):
        for ch in el:
            if ch.tag == "level4":
                yield from rec(ch, _parse_date(ch.find("front")))
            elif ch.tag == "level5":
                yield _article(ch, book, date, path.name)
            elif ch.tag.startswith("level"):
                yield from rec(ch, date)

    yield from rec(root, None)


def iter_files(directory: str | Path, books: tuple[str, ...] | None = None) -> list[Path]:
    out = []
    for p in sorted(Path(directory).glob("2nd_w*.xml")):
        m = _FILE.match(p.name)
        if m and (books is None or m.group(1) in books):
            out.append(p)
    return out
