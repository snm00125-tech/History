# 한국사 타임라인 웹 서비스

날짜별로 한국사 기록(1차: 조선왕조실록)을 보여 주는 정적 웹 서비스.

## 핵심 규칙 (어기지 말 것)

1. **모든 기록은 율리우스적일(JDN, 정수)에 매단다.** 화면에는 양력·음력·왕력·간지를 함께 표시한다.
2. **양력 표기**: JDN 2299161(1582-10-15) 이후는 그레고리력, 이전은 율리우스력. 역산 그레고리력은 쓰지 않는다.
3. **타 기관 번역문은 저장하지도, 화면에 싣지도 않는다.** 원문(한문)에서 자체 요약을 만들고 원문 링크를 건다.
   - 수집 단계에서도 번역문 필드는 버린다. 작업 DB에 넣지 않는다.
4. **요약 = 원문에 있는 사실만.** 배경 설명은 **해설**에 따로 쓴다. 요약 문장마다 **근거 구절 위치**(기사 ID + 원문 문자 오프셋)를 저장한다.
5. **요약과 해설은 구축 단계에서 미리 만들어 저장한다.** 서비스에는 실시간 AI 호출이 없다.
6. **기능을 고친 뒤에는 매번 오류와 속도를 점검한다.** (`pytest`가 정확성과 속도 테스트를 함께 돈다.)
7. 모르는 것은 추측하지 말고 사용자에게 묻는다. 출처가 불확실한 값에는 `verified=False`처럼 표시를 남긴다.

## 구성

```
pipeline/        Python 스크립트 + SQLite 작업 DB
  hdate/         날짜 변환 (양력·음력·왕력·간지 ↔ JDN)
  sillok/        실록 원문 XML → 기사 단위 파서, SQLite 적재, 집계
  reports/       집계 결과
  tools/         일회성 생성 스크립트
  tests/
web/             Next.js + TypeScript 정적 사이트. 날짜별 JSON을 읽는다   (작업 예정)
```

파이프라인 단계: 수집 → 분리(기사 단위) → 날짜 정규화(JDN) → 분류 → 요약 → 용어 → 검수 → 내보내기(날짜별 JSON).

## 날짜 모듈 `pipeline/hdate`

- `calendar.py`: 양력 ↔ JDN. `solar_to_jdn`은 1582-10-05~14를 거부한다.
- `lunar.py`: 음력 ↔ JDN. 음력 1000~2050년.
  표 `lunar_data.py`는 korean-lunar-calendar 0.4.0(MIT, KASI 자료 기반)에서 `tools/build_lunar_table.py`로 생성했다. 직접 고치지 말 것.
  upstream의 기준일 "1000-02-13"은 역산 그레고리력이다(= 율리우스력 1000-02-08).
- `ganji.py`: 연·월·일 간지. 윤달은 월건이 없다(None).
- `regnal.py`: 조선 왕력. 유년칭원이 기본이고, 태조·세조·중종·인조는 즉위년칭원.
  선조 외 원년은 아직 미검증이고, 즉위일은 비어 있다. 실록 기사 머리와 대조해 채운다.
- `describe(jdn)` → 양력/음력/왕력/간지를 한 번에 돌려준다.

검증 예: `regnal_to_jdn("선조", 25, 4, 13)` = JDN 2302669 = 1592-05-23(그레고리력), 일진 임인.

## 실록 원문 `pipeline/sillok`

- 원자료: 공공데이터포털 15053647 「국사편찬위원회_조선왕조실록 정보_실록원문」(zip 143MB, XML 673개, 공공누리 1유형).
  내려받기: `https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000007640398&fileDetailSn=1`
  (atchFileId는 데이터 갱신 때 바뀐다. 상세 페이지 `/tcs/dss/selectFileDataDownload.do`에서 새로 얻는다.)
- 파일 `2nd_<실록ID>_<NNN>.xml`. wna=선조실록, wnb=선조수정실록. 계층은 level2 연 > level3 월 > level4 일(일진) > level5 기사.
- 기사 ID(level5 id)를 sillok.history.go.kr/id/<ID> 원문 링크로 쓴다.
- **level5의 국문 기사 제목(mainTitle)은 저장하지 않는다.** 국편의 번역 산물이다.
- 본문의 원주·교감주·사론·색인(인명·지명 등)·외자(〓)는 `span` 표에 위치(문자 오프셋)로 남긴다.
- 작업 DB: `pipeline/data/work.sqlite` (git 제외). 표 `article`과 `span`. `jdn_status`는 기사 일진과 계산 일진을 대조한 결과다.

### 음력 표와 실록 일진이 어긋나는 곳 (결정 대기)

선조실록·선조수정실록 28,577건 가운데 일진 대조 결과는 일치 28,328, 불일치 215, 날짜 불가 3, 일 미상 31이다.
- 선조실록 1592년 9월(108건)과 1602년 9월(83건)은 한 달 내내 +1일 어긋난다. 실록에는 8월 30일이 있고, 9월 초하루 일진이 KASI 표보다 하루 늦다.
  그런데 9월 30일 일진이 10월 초하루 일진과 같다(1592년 丁亥/丁亥, 1602년 己丑/己丑). 실록 자체가 모순된다.
- 선조수정실록 1597년 9월은 朔己丑인데, 선조실록과 KASI 표는 朔戊子다.
- 나머지는 대부분 한두 건짜리 오기(子/午 혼동 등)로 보인다.
현재는 KASI 표를 그대로 쓰고, 어긋난 기사는 `jdn_status='ganji_mismatch'`로 표시만 한다.

## 명령

```
cd pipeline && python3 -m pytest -q --durations=5
cd pipeline && python3 -I -m sillok.load data/raw/sillok_15053647/x data/work.sqlite wna wnb   # 적재 (약 4초)
cd pipeline && python3 -I -m sillok.validate data/raw/sillok_15053647/x wna wnb             # 일진 대조
cd pipeline && python3 -I -m sillok.report data/work.sqlite 1592 1598                        # 월별 집계
```

## 작업 원칙

- 내려받은 원자료는 `pipeline/data/raw/`에 두고 git에 넣지 않는다. 신뢰할 수 없는 데이터로 다루고, 파싱할 때는 `python -I`로 실행한다.
- 실록 기사 머리의 일진(간지)과 `hdate`가 계산한 일진을 전수 대조해 음력 표를 검증한다.
