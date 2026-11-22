// pipeline/sillok/export.py 가 만드는 JSON의 형태

export type Regnal = { king: string; year: number; ambiguous: boolean };

export type DateInfo = {
  jdn: number;
  solar: string; // YYYY-MM-DD
  solar_calendar: "gregorian" | "julian";
  lunar: { year: number; month: number; day: number; leap: boolean };
  regnal: Regnal[];
  ganji: { year: string; month: string | null; day: string };
};

export type Summary = {
  title: string;
  sentences: { text: string; evidence: [number, number][] }[];
  commentary: { text: string; verified: boolean }[];
  author: string;
  review_status: "draft" | "approved" | "rejected";
};

export type Article = {
  id: string;
  book: "wna" | "wnb";
  url: string;
  precision: "day" | "month" | "none";
  lunar_day: number | null;
  day_ganji_src: string | null;
  jdn: number | null;
  jdn_status: string;
  needs_review: boolean;
  text: string;
  notes: [string, number, number][];
  groups: string[];
  sources: [string, string][];
  summary: Summary | null;
};

export type MonthLunar = { year: number; month: number; leap: boolean };

export type MonthDoc = {
  key: string;
  lunar: MonthLunar;
  jdn_start: number;
  jdn_end: number;
  solar_start: string;
  solar_end: string;
  regnal: Regnal[];
  ganji: { year: string; month: string | null };
  days: { date: DateInfo; articles: Article[] }[];
  month_articles: Article[];
  prev: string | null;
  next: string | null;
};

export type IndexDay = {
  jdn: number;
  solar: string;
  lunar_day: number;
  day_ganji: string;
  n: number;
  summarized: number;
  titles: string[];
};

export type IndexMonth = {
  key: string;
  lunar: MonthLunar;
  jdn_start: number;
  jdn_end: number;
  solar_start: string;
  solar_end: string;
  regnal: Regnal[];
  ganji: { year: string; month: string | null };
  days: IndexDay[];
  n_month: number;
  n: number;
  summarized: number;
};

export type Index = {
  years: [number, number];
  books: Record<string, string>;
  groups: { key: string; name: string }[];
  months: IndexMonth[];
  n_articles: number;
  n_summarized: number;
  generated: string;
};
