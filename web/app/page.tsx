import Link from "next/link";
import { getIndex } from "@/lib/data";
import { lunarMonthLabel, regnalLabel } from "@/lib/format";
import DateJump from "@/components/DateJump";
import type { IndexMonth } from "@/lib/types";

export default function Home() {
  const idx = getIndex();
  const byYear = new Map<number, IndexMonth[]>();
  for (const m of idx.months) {
    const a = byYear.get(m.lunar.year) ?? [];
    a.push(m);
    byYear.set(m.lunar.year, a);
  }
  const days = idx.months.flatMap((m) => m.days.map((d) => d.jdn));
  const max = Math.max(...idx.months.map((m) => m.n));

  return (
    <>
      <section className="intro">
        <h1>날짜로 읽는 조선왕조실록</h1>
        <p>
          임진왜란 시기(1592~1598) 선조실록·선조수정실록 기사 {idx.n_articles.toLocaleString()}건을 날짜별로 모았습니다.
          모든 날에 양력·음력·왕력·간지를 함께 적고, 원문(한문)과 국사편찬위원회 원문 링크를 붙였습니다.
        </p>
        <p className="meta">
          자체 요약 {idx.n_summarized.toLocaleString()}건 (1592년 4~5월부터 차례로 늘려 가는 중). 요약이 없는 기사는 원문만 보입니다.
        </p>
        <DateJump days={days} min={idx.months[0].solar_start} max={idx.months[idx.months.length - 1].solar_end} />
      </section>

      {[...byYear.entries()].map(([y, ms]) => (
        <section key={y} className="year">
          <h2>
            {y}년 <span className="meta">{ms[0].ganji.year}년 · {regnalLabel(ms[0].regnal)}</span>
          </h2>
          <div className="months">
            {ms.map((m) => (
              <Link key={m.key} href={`/m/${m.key}/`} className="month-cell" style={{ ["--fill" as string]: `${Math.round((m.n / max) * 100)}%` }}>
                <span className="mname">{lunarMonthLabel(m.lunar)}</span>
                <span className="mcount">{m.n}건</span>
                {m.summarized > 0 && <span className="msum">요약 {m.summarized}</span>}
                <span className="bar" aria-hidden />
              </Link>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
