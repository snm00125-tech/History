// 데이터: public/data (pipeline/sillok/export.py 출력). 모든 화면은 이 파일들만 읽는다.

export type Summary = { title: string; sentences: string[]; commentary: string[]; author: string };

export type Article = {
  id: string;
  b: string; // 실록 코드 (wna 등)
  t: string; // 국사편찬위원회 국문 제목
  g: string[]; // 분류 묶음 코드
  x: string; // 원문(한문)
  s?: Summary; // 자체 요약
  r?: string; // 검수 필요 사유 (jdn_status)
  reg?: string; // 원자료 재위연도 (고종·순종, 고려·삼국)
  e?: 1; // 날짜가 추정 역법(1000년 이전)
  imp?: 1; // 국편 연표 중요도 1
  k?: number[]; // 제목에 나오는 용어 번호(terms.json)
  p?: [string, string][]; // 이 기사에 나오는 인물 [인물 ID, 한글 이름] (언급 많은 순, 최대 12)
  lunarMonth?: string | null; // month 정밀도 기사의 음력 달
  range?: [string, string];
};

export type Day = {
  jdn: number;
  solar: string; // YYYY-MM-DD
  cal: "G" | "J"; // 그레고리력 | 율리우스력
  lunar: string | null;
  leap: boolean;
  est?: boolean; // 음력이 추정 역법(1000년 이전)
  regnal: string[];
  ganji: [string | null, string | null, string | null];
  articles: Article[];
  events?: { name: string; desc: string; anchor: string }[];
};

export type EventItem = {
  name: string;
  era: string;
  desc: string;
  anchor: string;
  jdn: number;
  solar: string;
  lunar: string | null;
  regnal: string[];
  verified: boolean;
};

export type MonthFile = { ym: string; days: Day[]; monthly: Article[] };
export type MonthEntry = { ym: string; n: number; kings: string[] };
export type Index = {
  books: Record<string, string>;
  groups: Record<string, string>;
  months: MonthEntry[];
  kings: { king: string; first: string }[];
  total: number;
  yearFile?: [number, number];
  undated: number;
  summarized: number;
};
export type OtdItem = { y: string; id: string; b: string; t: string };

const cache = new Map<string, Promise<unknown>>();

function get<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(`/data/${path}`).then((r) => {
        if (!r.ok) throw new Error(`${path}: ${r.status}`);
        return r.json();
      }),
    );
  }
  return cache.get(path) as Promise<T>;
}

export const loadIndex = () => get<Index>("index.json");
/** 1392년 전·1910년 뒤는 달 파일을 해 파일(y/<연>.json)로 묶었다(사이트 파일 수 한도) */
export const loadMonth = async (ym: string): Promise<MonthFile> => {
  const [y] = parseYmd(ym);
  const [before, after] = (await loadIndex()).yearFile ?? [-99999, 99999];
  if (y < before || y > after) {
    const yf = await get<Record<string, MonthFile>>(`y/${ym.slice(0, -3)}.json`);
    if (!yf[ym]) throw new Error(`${ym}: 없음`);
    return yf[ym];
  }
  return get<MonthFile>(`m/${ym}.json`);
};
export const loadOtd = (md: string) => get<OtdItem[]>(`otd/${md}.json`);
export const loadEvents = () => get<EventItem[]>("events.json");

export type KingItem = {
  king: string;
  book: string;
  start: string; // 그 왕 실록 첫 날짜 기사 (양력)
  end: string;
  jdnStart: number;
  jdnEnd: number;
  articles: number;
  years: Record<string, number>; // 양력 연도 → 그 왕 실록 기사 수
  events: { name: string; solar: string }[];
};
export const loadKings = () => get<KingItem[]>("kings.json");

/** 원문 사이트: 실록(w로 시작)은 조선왕조실록 사이트, 그 밖은 한국사데이터베이스 */
export const sourceUrl = (id: string) =>
  id.startsWith("w")
    ? `https://sillok.history.go.kr/id/${id}`
    : id.startsWith("SJW-")
      ? `https://sjw.history.go.kr/id/${id}`
      : `https://db.history.go.kr/id/${id.replace(/_d\d\d(m\d\d)?$/, "")}`; // 일기를 날로 나눈 조각은 원래 요소로
export const sourceSite = (id: string) =>
  id.startsWith("w") ? "조선왕조실록 사이트" : id.startsWith("SJW-") ? "승정원일기 사이트" : "한국사데이터베이스";

/** "1592-05-23", "-057-04" 등 → [연, 월, 일]. 연은 역사 연도(기원전 = 음수, 0년 없음) */
export function parseYmd(s: string): number[] {
  const m = /^(-?\d+)-(\d+)(?:-(\d+))?/.exec(s);
  return m ? [Number(m[1]), Number(m[2]), m[3] ? Number(m[3]) : 0] : [NaN, NaN, NaN];
}
/** 역사 연도 → 천문 연도(달력 계산용) */
export const astroYear = (y: number) => (y < 0 ? y + 1 : y);
export const yearLabel = (y: number) => (y < 0 ? `기원전 ${-y}년` : `${y}년`);
export const ymKey = (ym: string) => {
  const [y, m] = parseYmd(ym);
  return y * 100 + m;
};
export const ymLabel = (ym: string) => {
  const [y, m] = parseYmd(ym);
  return `${yearLabel(y)} ${m}월`;
};

export function formatSolar(d: Day): string {
  const [y, m, dd] = parseYmd(d.solar);
  return `${yearLabel(y)} ${m}월 ${dd}일`;
}

export function formatLunar(d: Day): string {
  if (!d.lunar) return "";
  const [y, m, dd] = parseYmd(d.lunar);
  return `음력 ${yearLabel(y)} ${d.leap ? "윤" : ""}${m}월 ${dd}일${d.est ? "(추정)" : ""}`;
}

export function formatGanji(d: Day): string {
  const [y, m, dd] = d.ganji;
  return [y && `${y}년`, m && `${m}월`, dd && `${dd}일`].filter(Boolean).join(" ");
}

export const REVIEW_LABEL: Record<string, string> = {
  ganji_adjusted: "일진에 맞춰 날짜 조정",
  ganji_conflict: "일진 불일치",
  invalid_date: "날짜 오류",
  solar_conflict: "원자료 양력과 음력 불일치",
};

export type Term = { t: string; h: string; c: string; d: string; verified: boolean };
export const loadTerms = () => get<Term[]>("terms.json");
