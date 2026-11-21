// 양력 ↔ JDN (pipeline/hdate/calendar.py와 같은 규칙: 1582-10-15 이후 그레고리력, 이전 율리우스력)

const GREG_START = 2299161;

function gregToJdn(y: number, m: number, d: number) {
  const a = Math.floor((14 - m) / 12);
  const yy = y + 4800 - a;
  const mm = m + 12 * a - 3;
  return d + Math.floor((153 * mm + 2) / 5) + 365 * yy + Math.floor(yy / 4) - Math.floor(yy / 100) + Math.floor(yy / 400) - 32045;
}

function julToJdn(y: number, m: number, d: number) {
  const a = Math.floor((14 - m) / 12);
  const yy = y + 4800 - a;
  const mm = m + 12 * a - 3;
  return d + Math.floor((153 * mm + 2) / 5) + 365 * yy + Math.floor(yy / 4) - 32083;
}

export function solarToJdn(y: number, m: number, d: number) {
  const g = gregToJdn(y, m, d);
  return g >= GREG_START ? g : julToJdn(y, m, d);
}

/** 그 양력 달의 실제 날짜들 (1582년 10월은 5~14일이 없다) */
export function daysOfMonth(y: number, m: number): { day: number; jdn: number }[] {
  const out: { day: number; jdn: number }[] = [];
  for (let d = 1; d <= 31; d++) {
    if (y === 1582 && m === 10 && d >= 5 && d <= 14) continue;
    const j = solarToJdn(y, m, d);
    // 달이 넘어가면 멈춘다: 다음 달 1일의 JDN 이상이면 끝
    const nextFirst = m === 12 ? solarToJdn(y + 1, 1, 1) : solarToJdn(y, m + 1, 1);
    if (j >= nextFirst) break;
    out.push({ day: d, jdn: j });
  }
  return out;
}

/** 0 = 일요일 */
export const weekday = (jdn: number) => (jdn + 1) % 7;
