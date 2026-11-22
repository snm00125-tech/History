"""국편 한국사데이터베이스의 편년 사서 → 작업 DB.

  kr = 고려사(15053637)       세가 등. 음력·양력(율리우스)·일간지가 다 있다.
  kj = 고려사절요(15115521)   음력(대개 달 단위).
  sg = 삼국사기(15053635)     음력, 대개 달·해 단위. 기원전 연도는 '-0057'(= 기원전 57년).
  th = 국편 「오늘의 역사」 연표(15053642), 918~2008. 1897년부터는 양력.

    python3 -m sillok.load_kh data/raw data/work.sqlite

날짜:
- 1000년 이후 음력은 KASI 표(hdate.lunar), 그 전은 추정 역법(hdate.ancient) → jdn_status에 'est'를 붙인다.
- 원자료에 양력(율리우스)이 있으면 그것을 쓴다(고려사: 1000년 이후 KASI 표와 99.98% 일치 확인).
- 일간지(일진)가 있으면 ±2일 안에서 맞춘다(실록과 같은 규칙).
- 달 미상 = 'year' 정밀도(그해 전체), 일 미상 = 'month'.
연도는 천문 연도로 저장한다(기원전 1년 = 0).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from hdate import ancient, ganji, lunar
from hdate.calendar import julian_to_jdn, solar_to_jdn
from .load import MAX_ADJUST, SCHEMA
from .load_sa import BOOK_SCHEMA, _join_surrogates
from .parse import _article_text

SOURCES = {  # 책 코드 → (이름, 원자료 폴더, 파일 무늬)
    "sg": ("삼국사기", "khdb_15053635", "sg_*.xml"),
    "kr": ("고려사", "khdb_15053637", "kr_*.xml"),
    "kj": ("고려사절요", "khdb_15115521", "kj_*.xml"),
    "th": ("국편 연표(오늘의 역사)", "hist_15053642", "th.xml"),
    "ko": ("한국고대사료집성(중국 사서)", "khdb_15053631", "ko_*.xml"),
    "dh": ("자료대한민국사", "khdb_15099108", "dh_*.xml"),
}
_LDATE = re.compile(r"^(-?\d{1,4})-(\d\d)-(\d\d)L(\d)$")
_SDATE = re.compile(r"^(-?\d{1,4})-(\d\d)-(\d\d)$")
_GZ = re.compile(r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")
_KINGDOM = {"新羅": "신라", "高句麗": "고구려", "髙句麗": "고구려", "百濟": "백제"}
_REIGN = re.compile(r"(원|\d+)년")
# 국편 고대 분류 첫 단계 → 화면 묶음
_ANCIENT_GROUP = {"정치": "정치·행정", "군사": "전쟁·군사", "외교": "외교", "경제": "경제·산업", "사회": "사회·생활",
                  "문화": "문화·역사", "사상": "문화·역사", "종교": "문화·역사", "과학": "자연현상·과학",
                  "자연": "자연현상·과학", "천문": "자연현상·과학", "인물": "인사", "왕실": "왕실"}


def astro_year(y: int) -> int:
    """원자료 연도(기원전 = 음수, 0년 없음) → 천문 연도."""
    return y + 1 if y < 0 else y


def _parse(path: Path):
    raw = path.read_bytes()
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return ET.fromstring(_join_surrogates(raw.decode("utf-8")))


def _lunar_jdn(y: int, m: int, d: int, leap: bool) -> tuple[int, bool]:
    """→ (JDN, 추정?)."""
    if y >= lunar.BASE_YEAR:
        return lunar.lunar_to_jdn(y, m, d, leap), False
    return ancient.lunar_to_jdn(y, m, d, leap), True


def _month_range(y: int, m: int, leap: bool) -> tuple[int, int, bool]:
    if y >= lunar.BASE_YEAR:
        s = lunar.lunar_to_jdn(y, m, 1, leap)
        return s, s + lunar.month_length(y, m, leap) - 1, False
    s, e = ancient.month_range(y, m, leap)
    return s, e, True


def _year_range(y: int) -> tuple[int, int, bool]:
    if lunar.BASE_YEAR <= y < lunar.LAST_YEAR:
        return lunar.lunar_to_jdn(y, 1, 1), lunar.lunar_to_jdn(y + 1, 1, 1) - 1, False
    s, e = ancient.year_range(y)
    return s, e, True


def date_fields(y, m, d, leap, solar=None, gz=None):
    """→ dict(jdn, jdn_table, status, delta, review, precision, start, end, leap)."""
    out = dict(jdn=None, jdn_table=None, status="no_date", delta=None, review=0, precision="none",
               start=None, end=None, leap=leap)
    if y is None:
        return out
    est = False
    try:
        if m is None:
            s, e, est = _year_range(y)
            out.update(status="no_month", precision="year", start=s, end=e)
        elif d is None:
            try:
                s, e, est = _month_range(y, m, leap)
            except ValueError:
                if not leap:
                    raise
                s, e, est = _month_range(y, m, False)
                out["leap"] = False
            out.update(status="no_day", precision="month", start=s, end=e)
        else:
            try:
                jt, est = _lunar_jdn(y, m, d, leap)
            except ValueError:
                if leap:  # 그해에 없는 윤달 → 평달
                    jt, est = _lunar_jdn(y, m, d, False)
                    out["leap"] = False
                else:
                    jt, est = _lunar_jdn(y, m, 1, leap)
                    jt += d - 1  # 작은달의 30일 등: 일진으로 맞춘다
            j, status, delta = jt, ("no_ganji" if gz is None else "ok"), None
            if solar is not None and (est or abs(solar - jt) <= MAX_ADJUST):  # 원자료 양력이 있으면 그것을 쓴다
                j, status = solar, "solar_src"
                delta = solar - jt
                est = False
            elif solar is not None:  # 1000년 이후 표와 크게 다르면 원자료 양력 오기로 보고 표 날짜를 쓴다
                status, delta = "solar_conflict", solar - jt
            if gz is not None:
                diff = (ganji.index_of(gz) - ganji.day_index(j) + 30) % 60 - 30
                if status == "solar_conflict":
                    pass
                elif diff and abs(diff) <= MAX_ADJUST:
                    j, status, delta = j + diff, "ganji_adjusted", (j + diff) - jt
                elif diff:
                    status = "ganji_conflict"
            out.update(jdn=j, jdn_table=jt, status=status, delta=delta, precision="day", start=j, end=j,
                       review=int(status in ("ganji_adjusted", "ganji_conflict", "solar_conflict") and not est))
    except ValueError:
        out.update(status="invalid_date", review=1)
        return out
    if est:
        out["status"] = "est_" + out["status"]
    return out


def _texts(el, tag):
    return [(x.get("type"), x.get("date"), (x.text or "").strip()) for x in el.findall(f"./front/biblioData/date/{tag}")]


def iter_book(code: str, root, fname: str):
    """→ (id, 국문 제목, 날짜 필드들, 원문, 왕력, 분류[])."""
    kingdom = None
    t1 = root.find("./front/biblioData/title/mainTitle")
    if code == "sg" and t1 is not None:
        kingdom = next((v for k, v in _KINGDOM.items() if (t1.text or "").startswith(k)), None)

    def walk(el, king):
        t = el.find("./front/biblioData/title/mainTitle")
        title = (t.text or "").strip() if t is not None else ""
        if code == "sg" and el.tag == "level2" and kingdom:
            king = _korean_king(el) or title.replace(" ", "")
        txt = el.find("text")
        dates = _texts(el, "dateOccured")
        if txt is not None and dates:
            lun = next(((ty, dt, tx) for ty, dt, tx in dates if dt and _LDATE.match(dt)), None)
            sol = next(((ty, dt, tx) for ty, dt, tx in dates if dt and _SDATE.match(dt)), None)
            gz = next((g[1] for ty, dt, tx in dates if ty == "일간지" and (g := _GZ.search(tx))), None)
            y = m = d = None
            leap = False
            solar_j = None
            if lun:
                g = _LDATE.match(lun[1])
                y, m, d, leap = astro_year(int(g[1])), int(g[2]), int(g[3]), g[4] == "1"
                if y >= 3000 or y == 0:  # 9999 = 연도 미상
                    y = None
                m = None if m in (0, 99) else m
                d = None if (m is None or d in (0, 99)) else d
            if sol:
                g = _SDATE.match(sol[1])
                sy, sm, sd = astro_year(int(g[1])), int(g[2]), int(g[3])
                if sm not in (0, 99) and sd not in (0, 99):
                    try:
                        solar_j = julian_to_jdn(sy, sm, sd) if sy < 1582 else solar_to_jdn(sy, sm, sd)
                    except ValueError:
                        solar_j = None
                if not lun:  # 양력만 있는 기록(연표 1897~): 음력 칸은 양력 날짜로 바꿔 채운다
                    if solar_j is not None:
                        lu = lunar.jdn_to_lunar(solar_j)
                        y, m, d, leap = lu.year, lu.month, lu.day, lu.leap
                    elif sm not in (0, 99):
                        y, m, d = sy, sm, None
            if gz is None and code == "sg" and d is not None and txt is not None:
                head = "".join(txt.itertext())[:40]
                if (g2 := re.search(r"月\s*" + _GZ.pattern, head)):
                    gz = g2[1]
            f = date_fields(y, m, d, leap, solar_j if (lun or solar_j is not None) else None, gz)
            if sol and not lun and solar_j is not None:
                f["status"] = "solar"
            elif sol and not lun and solar_j is None and y is not None:  # 양력 달만: 그 양력 달 범위
                s = solar_to_jdn(y, m, 1)
                e = (solar_to_jdn(y + 1, 1, 1) if m == 12 else solar_to_jdn(y, m + 1, 1)) - 1
                f.update(status="solar_month", precision="month", start=s, end=e)
            reg = None
            if el.get("왕명") and el.get("재위년도"):
                kn = el.get("왕명").split("(")[0]
                ry = el.get("재위년도").split("(")[0]
                reg = f"고려 {kn} {ry}"
            elif code == "sg" and king and lun:
                r = _REIGN.search(lun[2])
                if r:
                    reg = f"{kingdom} {king} {'원년' if r[1] == '원' else r[1] + '년'}"
            subs = [(x.text or "").strip() for x in el.findall("./front/biblioData/subjectClass")
                    if (x.text or "").strip() and x.get("scheme") != "중요도"]
            imp = next((x.get("code") for x in el.findall("./front/biblioData/subjectClass")
                        if x.get("scheme") == "중요도"), None)
            text, spans = _article_text(txt)
            if code == "th" and not text.strip():
                text = title
            yield dict(id=el.get("id"), title=title, f=f, y=y, m=m, d=d, text=text, spans=spans, reg=reg,
                       subjects=subs, imp=imp, gz=gz, file=fname)
        for ch in el:
            if ch.tag.startswith("level"):
                yield from walk(ch, king)

    yield from walk(root, None)


_ACCESSION = re.compile(r"^(?:시조\s*)?(?:[가-힣]+왕의 [가-힣]+인\s*)?([가-힣]+?)(?:이|가) (?:즉위하다|왕위에 오르다)")


_KING_KO = {"文武王": "문무왕", "東明聖王": "동명성왕", "太祖大王": "태조대왕", "美川王": "미천왕", "寶藏王": "보장왕",
            "溫祚王": "온조왕", "法王": "법왕", "義慈王": "의자왕"}  # 즉위 제목이 없는 왕(표준 독음)


def _korean_king(el) -> str | None:
    """왕 단락 안 국편 국문 제목 「아달라이사금이 즉위하다」에서 한글 왕 이름."""
    t0 = el.find("./front/biblioData/title/mainTitle")
    if t0 is not None and (t0.text or "").strip().replace(" ", "") in _KING_KO:
        return _KING_KO[t0.text.strip().replace(" ", "")]
    for t in el.iter("mainTitle"):
        if (m := _ACCESSION.match((t.text or "").strip())):
            return m[1]
    return None


def groups_for(subjects: list[str]) -> list[str]:
    out = []
    for s in subjects:
        parts = re.split(r"[＞>]", s)
        for p in parts[:2]:
            g = _ANCIENT_GROUP.get(p.strip())
            if g and g not in out:
                out.append(g)
                break
    return out


def load_kh(raw: str, db: str, codes=None) -> dict:
    con = sqlite3.connect(db)
    con.executescript(SCHEMA + BOOK_SCHEMA)
    stats = {}
    with con:
        for code, (name, folder, pat) in SOURCES.items():
            if codes and code not in codes:
                continue
            files = sorted(p for p in (Path(raw) / folder / "x").rglob(pat))
            if not files:
                continue
            for t in ("span", "ref_title_ko", "subject", "article_group"):
                con.execute(f"DELETE FROM {t} WHERE article_id IN (SELECT id FROM article WHERE book=?)", (code,))
            con.execute("DELETE FROM article WHERE book=?", (code,))
            con.execute("DELETE FROM book WHERE code=?", (code,))
            rows, titles, spans, grps, subs, seen = [], [], [], [], [], set()
            for p in files:
                for a in iter_book(code, _parse(p), p.name):
                    if a["id"] in seen or not a["text"].strip():
                        continue
                    seen.add(a["id"])
                    f = a["f"]
                    src = json.dumps({"imp": a["imp"]}) if a["imp"] else "[]"
                    rows.append((a["id"], code, a["y"], a["m"], int(f["leap"]), a["d"], a["gz"], f["jdn"],
                                 f["jdn_table"], f["status"], f["delta"], f["review"], f["precision"], f["start"],
                                 f["end"], a["text"], json.dumps(a["subjects"], ensure_ascii=False), src, a["file"],
                                 a["reg"]))
                    if a["title"]:
                        titles.append((a["id"], a["title"]))
                    spans += [(a["id"], s.kind, s.start, s.end, s.ref) for s in a["spans"]]
                    grps += [(a["id"], g, i) for i, g in enumerate(groups_for(a["subjects"]))]
            con.executemany("INSERT INTO article (id,book,lunar_year,lunar_month,lunar_leap,lunar_day,day_ganji_src,"
                            "jdn,jdn_table,jdn_status,ganji_delta,needs_review,date_precision,jdn_start,jdn_end,text,"
                            "subjects,sources,file,regnal_src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.executemany("INSERT INTO ref_title_ko VALUES (?,?)", titles)
            con.executemany("INSERT INTO span VALUES (?,?,?,?,?)", spans)
            con.executemany("INSERT INTO article_group VALUES (?,?,?)", grps)
            con.execute("INSERT INTO book VALUES (?,?,?)", (code, name, "kh"))
            stats[code] = len(rows)
    con.close()
    return stats


if __name__ == "__main__":
    t = time.perf_counter()
    print(load_kh(sys.argv[1], sys.argv[2], tuple(sys.argv[3:]) or None), f"{time.perf_counter() - t:.1f}s")
