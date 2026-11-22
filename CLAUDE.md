# 한국사 타임라인 웹 서비스

날짜별로 한국사 기록(1차: 조선왕조실록)을 보여 주는 정적 웹 서비스.

## 핵심 규칙 (어기지 말 것)

1. **모든 기록은 율리우스적일(JDN, 정수)에 매단다.** 화면에는 양력·음력·왕력·간지를 함께 표시한다.
2. **양력 표기**: JDN 2299161(1582-10-15) 이후는 그레고리력, 이전은 율리우스력. 역산 그레고리력은 쓰지 않는다.
3. **개인판(사용자 혼자 쓰는 앱)이므로 타 기관 번역문·국문 제목을 저장하고 화면에 실어도 된다** (사용자 결정, 2026-11-21. 이전 규칙 "번역문 금지"를 대체).
   - 출처를 항상 함께 표시한다(예: 국사편찬위원회 국문 제목, 한국고전번역원 번역).
   - 수집은 공식 경로만 쓴다: 공공데이터 파일, 공개 API. 자동 접속을 막은 사이트(robots.txt 금지, 방화벽 차단)는 우회하거나 긁지 않는다.
     sillok.history.go.kr은 방화벽 차단, db.itkc.or.kr은 robots.txt 전체 금지(단 `/openapi/search`는 키 없이 열려 있고 기사명·번역 일부만 준다).
   - 국편 국문 기사 제목(`ref_title_ko`)은 화면·내보내기에 써도 된다. 자체 요약을 만들 때는 여전히 원문만 보고 쓴다(요약 입력에 번역문을 넣지 않는다).
   - 이 앱을 공개 배포하게 되면 이 규칙을 다시 정한다.
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
web/             Next.js + TypeScript 정적 사이트(output: export). public/data의 JSON만 읽는다
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
- level5의 국문 기사 제목(mainTitle)은 국편의 번역 산물이다. `ref_title_ko`에 둔다. 규칙 3 변경으로 화면·내보내기에 써도 된다(출처 표시).
- 선조수정실록(wnb)은 별도 출처로 선조실록(wna)과 함께 표시한다(`article.book`).
- 본문의 원주·교감주·사론·색인(인명·지명 등)·외자(〓)는 `span` 표에 위치(문자 오프셋)로 남긴다.
- 작업 DB: `pipeline/data/work.sqlite` (git 제외). **실록 전체 380,974건**(태조~철종, 적재 약 4분. 고종·순종실록은 별도 데이터 15053646이라 아직 없음). 표 `article`과 `span`.
  모든 기사에 국편 국문 제목(`ref_title_ko`)이 있다 → 화면 제목으로 바로 쓴다. 날짜 ok 99.2%. `jdn_status`는 기사 일진과 계산 일진을 대조한 결과다.

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

## 내보내기·웹

- `sillok/export.py`: DB → `web/public/data/` (git 제외, 약 316MB, 11초). `index.json`, `m/YYYY-MM.json`(양력 달별·날별 기사), `otd/MM-DD.json`(오늘의 실록), `undated.json`.
  기사: 국편 국문 제목, 분류, 원문, 자체 요약(있으면), 검수 표시. 고종·순종은 원자료 재위연도 표기를 왕력으로 쓴다.
- 고종·순종실록(15053646, 공공누리 4유형): 1896년(고종 33)부터 양력 날짜(간지 칸 '陽曆') → `jdn_status='solar'`. 고종 1874·1875·1893년 일진 불일치 192건은 원자료 머리 일진 오류로 보여 표 날짜 유지.
- 화면: `/`(날짜로 찾기, 왕별, 오늘의 실록), `/view/?ym=YYYY-MM&d=D`(달력 + 그날 기사, 분류 필터, 펼치면 요약·원문·실록 사이트 링크).
- 전체 기사 515,332건 = 실록 413,771(태조~순종 부록) + 비변사등록 93,528 + 한국사료총서 8,033, 6,536개월. 요약은 1592년만(사용자 결정: 나머지는 국편 제목만).
- 비변사등록(15053636, `sillok/load_bb.py`, book=bb): level4 단위, 음력 날짜(일 00이면 month), 일진 없음(no_ganji). 링크는 db.history.go.kr/id/<ID>.
- 한국사료총서(15053632, `sillok/load_sa.py`, book=sa017 등, `book` 표에 책 이름): 15책 8,033건 적재.
  · 구조화 날짜(dateOccured)가 있는 14책(청대일기·심원권일기·퇴수재일기·조보·경와집략·경와만록·남천일록 등, 대부분 조선 후기·근대). 음력으로 읽고, 일 99/00은 month.
  · 쇄미록(sa_017, 오희문, 1592~1601) 2,641건: 연(간지) 제목 > 월 제목 > 본문 「初二日」로 날을 나눔(`PARSED_BOOKS`, 날 번호가 앞으로만 갈 때만 인정). 기사 ID 끝 `_dNN`.
  · 날짜가 제목뿐인 기사는 본문 첫머리를 제목에 붙인다(`nice_title`).
  · 남은 책(임진기록·용사잡록·계암일록·묵재일기·윤치호일기 등 100여 책)은 날짜 표기가 제각각이라 미적재. 같은 방식으로 PARSED_BOOKS에 넣어 늘린다.
- 각사등록(15053638, 날짜 필드 없음, 미적재).
- **우선순위(사용자 결정)**: 조선 전반에 중요한 것을 먼저, 덜 중요한 개인 일기류는 나중에.
- **조선 주요 사건** `pipeline/events/joseon.json`(55건): 각 사건을 실록 기사(anchor)에 묶고 그 기사 날짜를 쓴다. 수정실록처럼 달 단위 기사면 `lunar`로 날짜를 지정.
  설명(desc)은 이 앱이 쓴 해설 → verified=false, 화면에 "해설(검수 전)" 표시. 내보내기 `events.json` + 그날 `days[].events`.
  화면: 첫 화면 「조선 주요 사건」(시기별), 달력 ★ 표시, 그날 상단 사건 상자.
- **제목 검색** `/search/?q=`(`sillok/search_index.py` → `data/s/`): 51만 제목의 두 글자 색인(crc32 % 2048 조각, 차분 부호화) + 문서 덩어리(2,000건씩).
  질의 두 글자 목록 교집합 → 제목에 질의가 그대로 든 것만, 날짜순 100건씩. 흔한 두 글자(df ≥ 15,000, 63개: '하다' 등)는 색인에서 빼고 건너뛴다. 한 글자 검색은 안 된다.
  결과를 누르면 `/view/…#기사ID`로 가서 그 기사를 펼치고 화면으로 가져온다. 파일 약 9,200개(Cloudflare 무료 한도 20,000 안).
- **인물** (공공데이터 15053645 실록 부가정보 인물·관직 CSV, `sillok/load_person.py`, `sillok/export_person.py`):
  표 person(115,859명), person_office(관직 336,255건, 관직 CSV의 기사 ID kma_… → wma_…), article_person(879,161쌍 = 원문 인명 색인 span ref M_… 묶음).
  내보내기 `p/<번호//500>.json`(인물 정보·관직·기사 문서 번호), `pi/<초성>.json`(이름 찾기, 언급 많은 순), 기사마다 `p`(나오는 인물 최대 12).
  화면: `/person/?id=M_…`(정보·관직 기록·나오는 기사 날짜순), 검색 화면 위에 「인물」 결과(같은 이름 여러 명을 생몰년·구분·기사 수로 구분), 기사 펼치면 「나오는 인물」 버튼.
- **왕별 연표** `/kings/`(`kings.json`): 27왕, 재위 막대 = 그 왕 실록의 첫~끝 기사(양력). 펼치면 연도별 그 왕 실록 기사 수 막대(누르면 그해 첫 달로), 재위 중 주요 사건.
  난중일기·징비록은 공공데이터에 없다.
- 글꼴: Pretendard(npm `pretendard`, 사이트에 내장).

## 남은 일 (사용자에게 다시 알릴 것)

- **배포 대기**: Cloudflare 계정 fa49726b79350a5b7137af2f93dedcbc, workers.dev 하위 도메인 oreum-cloud → 주소 https://history.oreum-cloud.workers.dev (`web/wrangler.jsonc`).
  토큰이 History 환경의 "네트워크 비밀값"으로 저장돼 있으면 프록시가 Authorization 헤더를 덮어써 wrangler 자산 업로드(임시 JWT)가 401로 실패한다.
  사용자가 할 일: 환경 설정에서 네트워크 비밀값 'Cloudflare API token (history-deploy)' 삭제 → 환경 변수 `CLOUDFLARE_API_TOKEN` 추가 → 새 세션.
  그 뒤: 원자료 내려받기·적재·export → `cd web && npm run build && npx wrangler deploy`. (api.cloudflare.com은 허용 주소에 추가됨)
- 사용자가 채팅에 토큰을 한 번 붙여 넣었다(이전 토큰, 삭제 권함).

## 명령

```
cd pipeline && python3 -m pytest -q --durations=5
cd pipeline && python3 -m sillok.load data/raw/sillok_15053647/x data/work.sqlite            # 전체 적재 (약 4분, 그 뒤 summaries/*.jsonl 재적재)
cd pipeline && python3 -m sillok.validate data/raw/sillok_15053647/x wna wnb             # 일진 대조
cd pipeline && python3 -m sillok.report data/work.sqlite 1592 1598                        # 월별 집계
cd pipeline && python3 -m sillok.summary data/work.sqlite summaries/pilot_1592_04.jsonl  # 요약 검증·적재
cd pipeline && python3 -m sillok.review data/work.sqlite reports/pilot_1592_04_review.md 1592 4  # 검수 문서
cd pipeline && .venv/bin/python -m sillok.generate prepare data/work.sqlite t1592_05 --years 1592 1592 --months 5  # 요청 준비
cd pipeline && .venv/bin/python -m sillok.generate submit|status|collect|retry data/work.sqlite t1592_05
cd pipeline && python3 -m sillok.load data/raw/sillok_15053646/x data/work.sqlite            # 고종·순종 추가 적재 (약 40초)
cd pipeline && python3 -m sillok.load_bb data/raw/khdb_15053636/x data/work.sqlite          # 비변사등록 적재 (약 6초)
cd pipeline && python3 -m sillok.load_sa data/raw/khdb_15053632/x data/work.sqlite          # 한국사료총서 적재 (약 8초)
cd pipeline && python3 -m sillok.load_person data/raw/person_15053645/x data/work.sqlite   # 인물 (실록 적재 뒤, 약 5초)
cd pipeline && python3 -m sillok.export data/work.sqlite ../web/public/data                 # 웹 데이터 내보내기
cd web && npm install && npm run dev        # 개발 서버 :3000
cd web && npm run build                     # 정적 사이트 → web/out
```

## 작업 원칙

- 개인판이므로 프로젝트 규칙은 앱 구현이 쉬워지는 쪽으로 바꿔도 된다(사용자 결정). 바꾼 규칙은 이 파일에 적는다. 단 외부 사이트의 접근 차단(방화벽·robots.txt)은 우회하지 않는다.

- 사용자에게 보내는 작업 중 설명과 결과 보고는 모두 한국어로 쓴다.
- 내려받은 원자료는 `pipeline/data/raw/`에 두고 git에 넣지 않는다. 신뢰할 수 없는 데이터로 다룬다. 원자료 디렉터리 안에서 스크립트를 실행하지 않는다.
- 실록 기사 머리의 일진(간지)과 `hdate`가 계산한 일진을 전수 대조해 음력 표를 검증한다.
