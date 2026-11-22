import type { DateInfo, MonthLunar, Regnal } from "./types";

export const BOOK_NAMES: Record<string, string> = { wna: "선조실록", wnb: "선조수정실록" };

export const GROUP_NAMES: Record<string, string> = {
  war: "전쟁·군사",
  diplomacy: "외교",
  politics: "정치·행정",
  personnel: "인사",
  royal: "왕실",
  law: "사법",
  economy: "경제·산업",
  society: "사회·생활",
  culture: "문화·역사",
  nature: "자연현상·과학",
};

export function solarLabel(iso: string, cal?: "gregorian" | "julian"): string {
  const [y, m, d] = iso.split("-").map(Number);
  const s = `${y}년 ${m}월 ${d}일`;
  return cal === "julian" ? `${s} (율리우스력)` : s;
}

export function lunarMonthLabel(l: MonthLunar): string {
  return `${l.leap ? "윤" : ""}${l.month}월`;
}

export function regnalLabel(r: Regnal[]): string {
  return r.map((x) => `${x.king} ${x.year}년`).join(" / ");
}

export function fullDate(d: DateInfo) {
  return {
    solar: solarLabel(d.solar, d.solar_calendar),
    lunar: `음력 ${d.lunar.year}년 ${d.lunar.leap ? "윤" : ""}${d.lunar.month}월 ${d.lunar.day}일`,
    regnal: regnalLabel(d.regnal),
    ganji: `${d.ganji.year}년${d.ganji.month ? ` ${d.ganji.month}월` : ""} ${d.ganji.day}일`,
  };
}

export const STATUS_NOTE: Record<string, string> = {
  ganji_adjusted: "기사 일진에 맞춰 날짜를 하루이틀 옮겼습니다 (검수 전)",
  ganji_conflict: "기사 일진과 역법 계산이 크게 어긋납니다 (검수 전)",
  invalid_date: "원문 날짜가 역법상 없는 날입니다 (검수 전)",
  no_day: "원문에 날이 적혀 있지 않습니다",
};

/** 양력 날짜 → JDN. 1582-10-15 이후 그레고리력, 이전 율리우스력. */
export function solarToJdn(y: number, m: number, d: number): number | null {
  const a = Math.floor((14 - m) / 12);
  const yy = y + 4800 - a;
  const mm = m + 12 * a - 3;
  const greg = y > 1582 || (y === 1582 && (m > 10 || (m === 10 && d >= 15)));
  if (y === 1582 && m === 10 && d > 4 && d < 15) return null;
  const base = d + Math.floor((153 * mm + 2) / 5) + 365 * yy + Math.floor(yy / 4);
  return greg ? base - Math.floor(yy / 100) + Math.floor(yy / 400) - 32045 : base - 32083;
}
