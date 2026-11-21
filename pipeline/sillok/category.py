"""분류: 국편 subjectClass(원자료 그대로) → 자체 상위 묶음(화면 필터용).

국편 분류 표기는 '대분류-세부(漢字)' 또는 '대분류(漢字)'. 대분류 한글명만 떼어 묶음에 대응시킨다.
묶음은 이 프로젝트가 정한 것이다(사실이 아니라 화면 설계). 바꿀 때는 GROUPS만 고친다.
"""
from __future__ import annotations

import re

# (묶음 키, 화면 이름, 국편 대분류들)
GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("war", "전쟁·군사", ("군사", "변란")),
    ("diplomacy", "외교", ("외교", "무역")),
    # '정치'는 국편 대분류에 없지만 원자료 오기 1건(세종 21년 '정치(政治)-왕실(王室)-종친(宗親)')이 있다
    ("politics", "정치·행정", ("정론", "행정", "호구", "정치")),
    ("personnel", "인사", ("인사",)),
    ("royal", "왕실", ("왕실",)),
    ("law", "사법", ("사법",)),
    ("economy", "경제·산업", ("재정", "농업", "상업", "공업", "광업", "수산업", "금융", "물가",
                             "도량형", "교통", "건설")),
    ("society", "사회·생활", ("구휼", "신분", "가족", "향촌", "풍속", "윤리", "보건", "의약",
                             "의생활", "식생활", "주생활")),
    ("culture", "문화·역사", ("사상", "교육", "출판", "어문학", "예술", "역사", "인물")),
    ("nature", "자연현상·과학", ("과학",)),
)
_MAJOR_TO_GROUP = {m: g for g, _, ms in GROUPS for m in ms}
GROUP_NAMES = {g: n for g, n, _ in GROUPS}
_SPLIT = re.compile(r"^([^-(]+)(?:\([^)]*\))?(?:-(.+))?$")


def split_subject(raw: str) -> tuple[str, str | None]:
    """'외교-왜(倭)' → ('외교', '왜(倭)'), '군사(軍事)' → ('군사', None)."""
    m = _SPLIT.match(raw.strip().removeprefix("【분류】"))  # 원자료 오기 1건(인조 13년)
    if not m:
        raise ValueError(f"분류 형식이 아님: {raw}")
    return m.group(1).strip(), m.group(2)


def group_of(raw: str) -> str:
    major, _ = split_subject(raw)
    g = _MAJOR_TO_GROUP.get(major)
    if g is None:
        raise ValueError(f"상위 묶음에 대응하지 않는 국편 대분류: {major} ({raw})")
    return g


def groups_of(subjects: list[str]) -> list[str]:
    """기사의 묶음들(국편 분류 순서대로, 중복 제거)."""
    out: list[str] = []
    for s in subjects:
        g = group_of(s)
        if g not in out:
            out.append(g)
    return out
