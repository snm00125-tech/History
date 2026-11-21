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
  reg?: string; // 원자료 재위연도 (고종·순종)
  lunarMonth?: string | null; // month 정밀도 기사의 음력 달
  range?: [string, string];
};

export type Day = {
  jdn: number;
  solar: string; // YYYY-MM-DD
  cal: "G" | "J"; // 그레고리력 | 율리우스력
  lunar: string | null;
  leap: boolean;
  regnal: string[];
  ganji: [string | null, string | null, string | null];
  articles: Article[];
};

export type MonthFile = { ym: string; days: Day[]; monthly: Article[] };
export type MonthEntry = { ym: string; n: number; kings: string[] };
export type Index = {
  books: Record<string, string>;
  groups: Record<string, string>;
  months: MonthEntry[];
  kings: { king: string; first: string }[];
  total: number;
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
export const loadMonth = (ym: string) => get<MonthFile>(`m/${ym}.json`);
export const loadOtd = (md: string) => get<OtdItem[]>(`otd/${md}.json`);

/** 원문 사이트: 실록(w로 시작)은 조선왕조실록 사이트, 그 밖은 한국사데이터베이스 */
export const sourceUrl = (id: string) =>
  id.startsWith("w") ? `https://sillok.history.go.kr/id/${id}` : `https://db.history.go.kr/id/${id}`;
export const sourceSite = (id: string) => (id.startsWith("w") ? "조선왕조실록 사이트" : "한국사데이터베이스");

export function formatSolar(d: Day): string {
  const [y, m, dd] = d.solar.split("-").map(Number);
  return `${y}년 ${m}월 ${dd}일`;
}

export function formatLunar(d: Day): string {
  if (!d.lunar) return "";
  const [y, m, dd] = d.lunar.split("-").map(Number);
  return `음력 ${y}년 ${d.leap ? "윤" : ""}${m}월 ${dd}일`;
}

export function formatGanji(d: Day): string {
  const [y, m, dd] = d.ganji;
  return [y && `${y}년`, m && `${m}월`, dd && `${dd}일`].filter(Boolean).join(" ");
}

export const REVIEW_LABEL: Record<string, string> = {
  ganji_adjusted: "일진에 맞춰 날짜 조정",
  ganji_conflict: "일진 불일치",
  invalid_date: "날짜 오류",
};
