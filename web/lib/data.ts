// 빌드 때만 쓰는 자료 읽기 (서버 컴포넌트 전용)
import fs from "node:fs";
import path from "node:path";
import type { Article, DateInfo, Index, MonthDoc } from "./types";

const DATA = path.join(process.cwd(), "data");

let indexCache: Index | null = null;
const monthCache = new Map<string, MonthDoc>();

export function getIndex(): Index {
  if (!indexCache) indexCache = JSON.parse(fs.readFileSync(path.join(DATA, "index.json"), "utf8"));
  return indexCache!;
}

export function getMonth(key: string): MonthDoc {
  let m = monthCache.get(key);
  if (!m) {
    m = JSON.parse(fs.readFileSync(path.join(DATA, "months", `${key}.json`), "utf8")) as MonthDoc;
    monthCache.set(key, m);
  }
  return m;
}

export type DayEntry = { date: DateInfo; articles: Article[]; monthKeys: string[] };

let dayCache: Map<number, DayEntry> | null = null;
let dayOrder: number[] = [];

/** JDN → 그날 기사. 같은 JDN이 두 달 파일에 있을 수 있어(일진 조정) 합친다. */
export function getDays(): Map<number, DayEntry> {
  if (dayCache) return dayCache;
  const map = new Map<number, DayEntry>();
  for (const im of getIndex().months) {
    for (const d of getMonth(im.key).days) {
      const e = map.get(d.date.jdn);
      if (e) {
        e.articles.push(...d.articles);
        if (!e.monthKeys.includes(im.key)) e.monthKeys.push(im.key);
      } else {
        map.set(d.date.jdn, { date: d.date, articles: [...d.articles], monthKeys: [im.key] });
      }
    }
  }
  dayOrder = [...map.keys()].sort((a, b) => a - b);
  dayCache = map;
  return map;
}

export function neighborDays(jdn: number): { prev: number | null; next: number | null } {
  getDays();
  const i = dayOrder.indexOf(jdn);
  return {
    prev: i > 0 ? dayOrder[i - 1] : null,
    next: i >= 0 && i + 1 < dayOrder.length ? dayOrder[i + 1] : null,
  };
}
