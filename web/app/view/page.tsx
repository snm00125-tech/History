"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArticleCard } from "@/app/ArticleCard";
import { daysOfMonth, weekday } from "@/lib/cal";
import {
  type Day,
  type Index,
  type MonthFile,
  formatGanji,
  formatLunar,
  formatSolar,
  loadIndex,
  loadMonth,
} from "@/lib/data";

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];

function ViewInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const ym = sp.get("ym") ?? "1592-05";
  const dParam = sp.get("d");
  const [idx, setIdx] = useState<Index | null>(null);
  const [mf, setMf] = useState<MonthFile | null>(null);
  const [missing, setMissing] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);
  const [bookFilter, setBookFilter] = useState<string | null>(null);

  useEffect(() => {
    loadIndex().then(setIdx);
  }, []);
  useEffect(() => {
    setMf(null);
    setMissing(false);
    loadMonth(ym)
      .then(setMf)
      .catch(() => setMissing(true));
  }, [ym]);

  const [y, m] = ym.split("-").map(Number);
  const byDay = useMemo(() => {
    const map = new Map<number, Day>();
    mf?.days.forEach((d) => map.set(Number(d.solar.slice(8)), d));
    return map;
  }, [mf]);

  // 선택한 날: 주소의 d, 없으면 그달 첫 기사 날
  const selDay = dParam ? Number(dParam) : mf?.days[0] ? Number(mf.days[0].solar.slice(8)) : null;
  const sel = selDay != null ? byDay.get(selDay) : undefined;

  // 기사 있는 앞뒤 달
  const pos = idx?.months.findIndex((x) => x.ym === ym) ?? -1;
  const nearest = useMemo(() => {
    if (!idx || pos >= 0) return null;
    return idx.months.find((x) => x.ym > ym) ?? null;
  }, [idx, pos, ym]);
  const prev = idx && pos > 0 ? idx.months[pos - 1].ym : null;
  const next = idx && pos >= 0 && pos < idx.months.length - 1 ? idx.months[pos + 1].ym : null;

  // 기사 있는 앞뒤 날 (달을 넘어감)
  const dayList = mf?.days ?? [];
  const di = sel ? dayList.indexOf(sel) : -1;
  const prevDay = di > 0 ? dayList[di - 1] : null;
  const nextDay = di >= 0 && di < dayList.length - 1 ? dayList[di + 1] : null;

  const grid = useMemo(() => {
    if (!y || !m) return [];
    const days = daysOfMonth(y, m);
    if (!days.length) return [];
    const lead = weekday(days[0].jdn);
    return [...Array(lead).fill(null), ...days];
  }, [y, m]);

  const goto = (ymv: string, d?: number | string) =>
    router.push(`/view/?ym=${ymv}${d != null ? `&d=${Number(d)}` : ""}`);

  const books = idx?.books ?? {};
  const groups = idx?.groups ?? {};
  const shown = (sel?.articles ?? []).filter(
    (a) => (!filter || a.g.includes(filter)) && (!bookFilter || a.b === bookFilter),
  );
  const bookCounts = useMemo(() => {
    const c: Record<string, number> = {};
    sel?.articles.forEach((a) => (c[a.b] = (c[a.b] ?? 0) + 1));
    return c;
  }, [sel]);
  const groupCounts = useMemo(() => {
    const c: Record<string, number> = {};
    sel?.articles.forEach((a) => a.g.forEach((g) => (c[g] = (c[g] ?? 0) + 1)));
    return c;
  }, [sel]);

  return (
    <div className="view">
      <nav className="monthnav">
        <button disabled={!prev} onClick={() => prev && goto(prev)}>
          ◀ 이전 달
        </button>
        <h2>
          {y}년 {m}월
          {mf?.days[0] && <small> · {mf.days[0].regnal.join(" / ")}</small>}
        </h2>
        <button disabled={!next} onClick={() => next && goto(next)}>
          다음 달 ▶
        </button>
      </nav>

      {missing && (
        <p className="hint">
          이 달에는 기사가 없습니다.{" "}
          {nearest && (
            <Link href={`/view/?ym=${nearest.ym}`}>
              다음 기록: {nearest.ym.replace("-", "년 ")}월 →
            </Link>
          )}
        </p>
      )}

      {mf && (
        <div className="calendar">
          {WEEK.map((w) => (
            <div key={w} className="wk">
              {w}
            </div>
          ))}
          {grid.map((c, i) => {
            if (!c) return <div key={`e${i}`} className="cell empty" />;
            const d = byDay.get(c.day);
            const n = d?.articles.length ?? 0;
            return (
              <button
                key={c.day}
                className={`cell${n ? " has" : ""}${selDay === c.day ? " sel" : ""}`}
                disabled={!n}
                onClick={() => goto(ym, c.day)}
              >
                <span className="dnum">{c.day}</span>
                {d?.lunar && <span className="lnum">{Number(d.lunar.slice(8))}</span>}
                {n > 0 && <span className="cnt">{n}</span>}
              </button>
            );
          })}
        </div>
      )}

      {sel && (
        <section className="dayview">
          <div className="dayhead">
            <button disabled={!prevDay} onClick={() => prevDay && goto(ym, prevDay.solar.slice(8))}>
              ◀
            </button>
            <div>
              <h3>
                {formatSolar(sel)} <small>({sel.cal === "G" ? "그레고리력" : "율리우스력"})</small>
              </h3>
              <p>
                {formatLunar(sel)} · {sel.regnal.join(" / ")} · {formatGanji(sel)}
              </p>
            </div>
            <button disabled={!nextDay} onClick={() => nextDay && goto(ym, nextDay.solar.slice(8))}>
              ▶
            </button>
          </div>
          {Object.keys(bookCounts).length > 1 && (
            <div className="filters">
              <button className={!bookFilter ? "on" : ""} onClick={() => setBookFilter(null)}>
                모든 자료
              </button>
              {Object.entries(bookCounts).map(([b, n]) => (
                <button key={b} className={bookFilter === b ? "on" : ""} onClick={() => setBookFilter(b)}>
                  {books[b] ?? b} {n}
                </button>
              ))}
            </div>
          )}
          {Object.keys(groupCounts).length > 1 && (
            <div className="filters">
              <button className={!filter ? "on" : ""} onClick={() => setFilter(null)}>
                전체 {sel.articles.length}
              </button>
              {Object.entries(groupCounts).map(([g, n]) => (
                <button key={g} className={filter === g ? "on" : ""} onClick={() => setFilter(g)}>
                  {groups[g] ?? g} {n}
                </button>
              ))}
            </div>
          )}
          {shown.map((a) => (
            <ArticleCard key={a.id} a={a} books={books} groups={groups} />
          ))}
        </section>
      )}

      {mf && mf.monthly.length > 0 && (
        <section className="monthly">
          <h3>이 달에 몰아 적은 기사 ({mf.monthly.length}건)</h3>
          <p className="hint">선조수정실록처럼 한 달 치를 한 날에 모아 적었거나, 비변사등록 좌목처럼 달 단위로 적은 기사입니다.</p>
          {mf.monthly.map((a) => (
            <ArticleCard key={a.id} a={a} books={books} groups={groups} />
          ))}
        </section>
      )}
    </div>
  );
}

export default function ViewPage() {
  return (
    <Suspense fallback={<p className="hint">불러오는 중…</p>}>
      <ViewInner />
    </Suspense>
  );
}
