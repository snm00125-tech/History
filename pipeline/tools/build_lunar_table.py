"""korean-lunar-calendar(MIT, KASI 기반)의 원시 비트 표를 hdate/lunar_data.py로 옮긴다.

사용: python -I tools/build_lunar_table.py <korean_lunar_calendar.py 경로> > hdate/lunar_data.py
upstream 파일을 import하지 않고 ast로 상수만 읽는다.
"""
import ast
import sys

src = open(sys.argv[1], encoding="utf-8").read()
tree = ast.parse(src)
data = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "KOREAN_LUNAR_DATA" for t in node.targets
    ):
        data = ast.literal_eval(node.value)
assert data, "KOREAN_LUNAR_DATA not found"

print('"""음력 월 길이·윤달 표 (1000~2050 음력년).')
print()
print("출처: korean-lunar-calendar 0.4.0 (MIT, https://github.com/usingsky/korean_lunar_calendar_py),")
print("      한국천문연구원(KASI) 음양력 자료 기반. tools/build_lunar_table.py로 생성. 직접 고치지 말 것.")
print()
print("비트 구성(연도별 정수): bit 11..0 = 1~12월 대(30)/소(29), bit 15..12 = 윤달 월(0이면 없음),")
print("bit 16 = 윤달 대/소, bit 25..17 = 그 해 총 일수.")
print('"""')
print()
print("BASE_YEAR = 1000")
print("# 음력 1000-01-01 = 역산 그레고리력 1000-02-13 (= 율리우스력 1000-02-08)")
print("DATA = (")
for i in range(0, len(data), 8):
    print("    " + ", ".join(f"0x{v:08x}" for v in data[i : i + 8]) + ",")
print(")")
