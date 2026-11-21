# 한국사 타임라인 웹 서비스

날짜별로 한국사 기록(1차: 조선왕조실록)을 보여 주는 정적 웹 서비스.

## 핵심 규칙 (어기지 말 것)

1. **모든 기록은 율리우스적일(JDN, 정수)에 매단다.** 화면에는 양력·음력·왕력·간지를 함께 표시한다.
2. **양력 표기**: JDN 2299161(1582-10-15) 이후는 그레고리력, 이전은 율리우스력. 역산 그레고리력은 쓰지 않는다.
3. **타 기관 번역문은 저장하지도, 화면에 싣지도 않는다.** 원문(한문)에서 자체 요약을 만들고 원문 링크를 건다.
   - 수집 단계에서도 번역문 필드는 버린다. 작업 DB에 넣지 않는다.
   - 예외(사용자 결정): 국편 국문 기사 제목만 작업 DB의 `ref_title_ko` 표에 **검수 참고용**으로 둔다. 화면·내보내기·요약 입력에는 절대 쓰지 않는다.
4. **요약 = 원문에 있는 사실만.** 배경 설명은 **해설**에 따로 쓴다. 요약 문장마다 **근거 구절 위치**(기사 ID + 원문 문자 오프셋)를 저장한다.
5. **요약과 해설은 구축 단계에서 미리 만들어 저장한다.** 서비스에는 실시간 AI 호출이 없다.
6. **기능을 고친 뒤에는 매번 오류와 속도를 점검한다.** (`pytest`가 정확성과 속도 테스트를 함께 돈다.)
7. 모르는 것은 추측하지 말고 사용자에게 묻는다. 출처가 불확실한 값에는 `verified=False`처럼 표시를 남긴다.

## 구성

```
pipeline/        Python 스크립트 + SQLite 작업 DB
  hdate/         날짜 변환 (양력·음력·왕력·간지 ↔ JDN)
  sillok/        실록 원문 XML → 기사 단위 파서, SQLite 적재, 집계
  summaries/     요약 JSONL (git에 넣는다. 자체 저작물)
  reports/       집계 결과, 검수용 문서
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
  정종·태종·인종은 실록에 '즉위년'이 없다(즉위한 해 전체가 앞 왕의 마지막 해로 적힘).
  태조~철종의 원년·칭원법은 실록 원문과 대조해 검증했다(`tests/test_regnal_data.py`). 고종은 미검증.
  왕 교체 경계 = 공식 즉위일이 아니라 **그 왕 실록의 첫 날짜 기사**. 앞 왕 실록과 겹치는 며칠은 `labels_for()`가 두 왕력을 준다.
- `describe(jdn)` → 양력/음력/왕력/간지를 한 번에 돌려준다.

검증 예: `regnal_to_jdn("선조", 25, 4, 13)` = JDN 2302669 = 1592-05-23(그레고리력), 일진 임인.

## 실록 원문 `pipeline/sillok`

- 원자료: 공공데이터포털 15053647 「국사편찬위원회_조선왕조실록 정보_실록원문」(zip 143MB, XML 673개, 공공누리 1유형).
  내려받기: `https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000007640398&fileDetailSn=1`
  (atchFileId는 데이터 갱신 때 바뀐다. 상세 페이지 `/tcs/dss/selectFileDataDownload.do`에서 새로 얻는다.)
- 파일 `2nd_<실록ID>_<NNN>.xml`. wna=선조실록, wnb=선조수정실록. 계층은 level2 연 > level3 월 > level4 일(일진) > level5 기사.
- 기사 ID(level5 id)를 sillok.history.go.kr/id/<ID> 원문 링크로 쓴다.
- level5의 국문 기사 제목(mainTitle)은 국편의 번역 산물이다. `ref_title_ko`에만 둔다(검수 대조용, 내보내기 금지).
- 선조수정실록(wnb)은 별도 출처로 선조실록(wna)과 함께 표시한다(`article.book`).
- 본문의 원주·교감주·사론·색인(인명·지명 등)·외자(〓)는 `span` 표에 위치(문자 오프셋)로 남긴다.
- 작업 DB: `pipeline/data/work.sqlite` (git 제외). 표 `article`과 `span`. `jdn_status`는 기사 일진과 계산 일진을 대조한 결과다.

### 날짜 확정: 일진 우선 (사용자 결정)

- `jdn_table` = 실록의 음력 월일을 KASI 표로 바꾼 값. `jdn` = 확정 값.
- 기사 일진이 표 날짜와 ±2일(`MAX_ADJUST`) 안에서 맞으면 그 날을 `jdn`으로 삼는다 → `ganji_adjusted`.
- 차이가 더 크면 역법 차이가 아니라 일진 오기(子/午 혼동 등)로 보고 표 날짜를 유지한다 → `ganji_conflict`.
- `ganji_adjusted`·`ganji_conflict`·`invalid_date`는 `needs_review=1`이다. 검수 단계에서 사람이 확정한다.
- 알려진 사례: 선조실록 1592년 9월·1602년 9월은 한 달 내내 +1일이다(실록에는 8월 30일이 있음). 이 경우 9/30과 10/1이 같은 일진이라 같은 JDN이 된다.
  선조수정실록 1597년 9월은 朔己丑인데, 선조실록과 KASI 표는 朔戊子다.
  선조수정실록 1592년 3월 3일은 머리 일진이 甲子이지만, 본문 교감주는 癸亥다. 머리 일진이 틀린 경우도 있으니 검수 때 본문과 대조한다.
- 1592~1598 현황: 선조실록 ok 10,884 / adjusted 108 / 일 미상 7, 수정실록 ok 512 / adjusted 5 / conflict 2.

### 날짜 정밀도 (사용자 결정)

- `date_precision` = day | month | none, 범위 `jdn_start`~`jdn_end`. 타임라인 배치는 이 값을 쓴다.
- **선조수정실록(wnb)은 전부 month.** 수정실록은 그달 기사를 한 날(대개 초하루)에 몰아 적는다(432개월 중 418개월).
  예: 1592년 4월 29건이 모두 14일자인데 내용은 14~30일. 화면에는 그달 칸에 따로 보여 준다.
- 일 미상(`??`) 기사도 month. day면 jdn_start = jdn_end = jdn.
- 달 단위로 적는 실록이 더 나오면 `sillok/load.py`의 `MONTH_PRECISION_BOOKS`에 넣는다.

## 분류 `sillok/category.py`

- 국편 subjectClass 원본은 `subject` 표에 그대로 둔다(번역문 아님, 메타데이터).
- 화면 필터용 자체 상위 묶음 10개(`article_group`): 전쟁·군사, 외교, 정치·행정, 인사, 왕실, 사법, 경제·산업, 사회·생활, 문화·역사, 자연현상·과학.
  국편 대분류 40개를 모두 대응시켰다. 대응 안 되는 분류가 나오면 적재가 실패한다.

## 요약 `sillok/summary.py`

- 형식: 한 줄 제목(25자 이하) + 요약 문장 + 선택 해설.
- 문장 수 상한 = 원문 250자당 1문장, 최소 3, 최대 10(`max_sentences`). 사용자 결정: 내용이 많으면 더 써도 된다. 정확성이 우선이다.
- 문장마다 근거 구절 = **원문에서 글자 그대로 뽑은 한문 인용**. 적재할 때 원문에서 찾아 오프셋을 저장하고, 못 찾으면 거부한다.
- 국편 국문 제목과 같은 제목은 거부한다. 요약할 때 `ref_title_ko`를 보지 않는다.
- 해설은 원문 밖 지식이라 `verified=false`로 저장하고 검수에서 확인한다.
- 파일럿: `summaries/pilot_1592_04.jsonl`(1592년 4월 51건, 이 세션에서 직접 작성, author=pilot-session).
  검수 문서: `reports/pilot_1592_04_review.md`. 사용자가 형식을 승인했다.

## 요약 일괄 생성 `sillok/generate.py`

- Claude Message Batches API(표준가의 50%). 모델 `claude-opus-5-5`, adaptive thinking, effort high, JSON 스키마 출력.
- 지침은 `sillok/prompt.py`(PROMPT_VERSION). 모든 요청에서 같아 1시간 캐시로 공유한다. 파일럿 3건을 예시로 싣고, 국편 국문 제목은 넣지 않는다.
- 흐름: `prepare`(요청 파일·비용 추정, API 안 씀) → `submit`(돈 드는 단계) → `status` → `collect`(검증 통과분만 `summaries/<이름>.jsonl`·DB에 넣고 실측 비용 기록) → `retry`(실패분에 오류를 알려 재요청, 최대 2번).
- 작업 폴더 `pipeline/data/gen/<이름>/`(git 제외). 안전 거절(refusal)과 재요청 끝에 남은 실패는 사람이 검토한다.
- 실행은 `pipeline/.venv/bin/python`(anthropic SDK 설치됨). API 키는 History 환경의 환경 변수 `HISTORY_ANTHROPIC_API_KEY`(Anthropic 주소는 네트워크 비밀값으로 저장할 수 없음). 접속 주소는 `HISTORY_ANTHROPIC_BASE_URL`(기본 api.anthropic.com). 이 환경의 `ANTHROPIC_BASE_URL`은 Claude Code용이라 쓰지 않는다.
- 비용은 제출 전에 사용자 승인을 받는다. 작은 묶음을 먼저 돌려 기사당 실측 비용으로 전체를 다시 추정한다.

## 세션 안 요약 생성 `sillok/session_gen.py` (사용자 선호: API 대신 세션 사용량)

- `plan`으로 달 단위 묶음(최대 90건·25,000자)을 `data/gen/session/<묶음>.md`에 만든다. 1592~1598은 193개 묶음.
- 서브에이전트가 묶음을 읽고 `summaries/s_<묶음>.jsonl`에 쓴다. 지침은 `sillok/prompt.py`의 RULES와 예시를 따른다.
- `verify`(빠짐·중복·검증, DB에 안 씀) → `merge`(DB 적재). 동시에 여러 작업자가 돌아도 DB 쓰기는 merge에서만 한다.
- 시험(1592_05_a 90건, Sonnet 5.5 서브에이전트, 약 8.5분)과 Opus 표본 10건 비교: 사실 오류는 찾지 못했다. Opus가 핵심 사실을 조금 더 담고 해설이 더 친절하다.
  Sonnet은 해설에 추측("~로 보인다", 앞뒤 기사로 짐작한 인물)을 썼다 → 지침 v2에서 금지하고 해당 해설을 고쳤다.
  비교 문서: `reports/compare_1592_05_a_sonnet_opus.md`.
- **1592년 전체(1,335건) 세션 생성 완료**(Sonnet 서브에이전트 4개 동시, 묶음당 3~15분). 작업자가 확신 못 한 곳은 `reports/session_gen_review_notes.md`에 묶음별로 모은다(「우선 확인」 표시 = 추정성 해설·원문과 다르게 읽은 곳).
  서브에이전트 지시문은 RULES 출력 → 묶음 작성 → verify 통과까지 반복, merge·DB·git 금지. 메인 세션이 보고를 읽고 merge·커밋한다.
- API 비교시험(`reports/compare_1592_05_models.md`, 10건): Haiku는 인명·관직 오류 4건으로 부적합, Sonnet은 오류 없음. 비용 때문에 사용자가 세션 생성을 택했다.
- 국편 실록 사이트(sillok.history.go.kr)는 자동 접속을 방화벽으로 막는다. 번역문 공공데이터도 없다(2026-11 확인).
- 검수 메모: 李𥕏(외자 한자)은 독음을 확정하지 못해 한자로 두었다. 新苽는 참외/오이 해석이 갈렸다(검수 필요).

## 명령

```
cd pipeline && python3 -m pytest -q --durations=5
cd pipeline && python3 -m sillok.load data/raw/sillok_15053647/x data/work.sqlite wna wnb   # 적재 (약 8초)
cd pipeline && python3 -m sillok.validate data/raw/sillok_15053647/x wna wnb             # 일진 대조
cd pipeline && python3 -m sillok.report data/work.sqlite 1592 1598                        # 월별 집계
cd pipeline && python3 -m sillok.summary data/work.sqlite summaries/pilot_1592_04.jsonl  # 요약 검증·적재
cd pipeline && python3 -m sillok.review data/work.sqlite reports/pilot_1592_04_review.md 1592 4  # 검수 문서
cd pipeline && .venv/bin/python -m sillok.generate prepare data/work.sqlite t1592_05 --years 1592 1592 --months 5  # 요청 준비
cd pipeline && .venv/bin/python -m sillok.generate submit|status|collect|retry data/work.sqlite t1592_05
```

## 작업 원칙

- 사용자에게 보내는 작업 중 설명과 결과 보고는 모두 한국어로 쓴다.
- 내려받은 원자료는 `pipeline/data/raw/`에 두고 git에 넣지 않는다. 신뢰할 수 없는 데이터로 다룬다. 원자료 디렉터리 안에서 스크립트를 실행하지 않는다.
- 실록 기사 머리의 일진(간지)과 `hdate`가 계산한 일진을 전수 대조해 음력 표를 검증한다.
