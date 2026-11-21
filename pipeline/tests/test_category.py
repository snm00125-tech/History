import pytest

from sillok.category import GROUP_NAMES, GROUPS, group_of, groups_of, split_subject


def test_split():
    assert split_subject("외교-왜(倭)") == ("외교", "왜(倭)")
    assert split_subject("군사(軍事)") == ("군사", None)
    assert split_subject("【분류】농업-양전(量田)") == ("농업", "양전(量田)")


def test_groups():
    assert groups_of(["외교-왜(倭)", "군사(軍事)", "군사-전쟁(戰爭)"]) == ["diplomacy", "war"]
    assert group_of("과학-천기(天氣)") == "nature"
    with pytest.raises(ValueError):
        group_of("없는분류-x")
    majors = [m for _, _, ms in GROUPS for m in ms]
    assert len(majors) == len(set(majors))  # 한 대분류는 한 묶음에만
    assert len(GROUP_NAMES) == 10
