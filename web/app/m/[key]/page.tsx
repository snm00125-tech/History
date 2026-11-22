import type { Metadata } from "next";
import Link from "next/link";
import { getIndex, getMonth } from "@/lib/data";
import { lunarMonthLabel, regnalLabel, solarLabel } from "@/lib/format";
import ArticleList from "@/components/ArticleList";

type P = { params: Promise<{ key: string }> };

export function generateStaticParams() {
  return getIndex().months.map((m) => ({ key: m.key }));
}

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const m = getMonth((await params).key);
  return { title: `${m.lunar.year}년 음력 ${lunarMonthLabel(m.lunar)}` };
}

export default async function MonthPage({ params }: P) {
  const m = getMonth((await params).key);
  const wna = m.days;
  const wnb = m.month_articles.filter((a) => a.book === "wnb");
  const undated = m.month_articles.filter((a) => a.book !== "wnb");

  return (
    <>
      <nav className="crumbs">
        <Link href="/">전체</Link>
        {m.prev && <Link href={`/m/${m.prev}/`}>← 이전 달</Link>}
        {m.next && <Link href={`/m/${m.next}/`}>다음 달 →</Link>}
      </nav>
      <section className="date-head">
        <h1>{m.lunar.year}년 음력 {lunarMonthLabel(m.lunar)}</h1>
        <dl className="dates">
          <div><dt>양력</dt><dd>{solarLabel(m.solar_start)} ~ {solarLabel(m.solar_end)}</dd></div>
          <div><dt>왕력</dt><dd>{regnalLabel(m.regnal)}</dd></div>
          <div><dt>간지</dt><dd>{m.ganji.year}년{m.ganji.month ? ` ${m.ganji.month}월` : " (윤달)"}</dd></div>
        </dl>
      </section>

      <section>
        <h2>선조실록 · 날짜별</h2>
        {wna.length === 0 && <p className="meta">이 달 선조실록 날짜 기사가 없습니다.</p>}
        <ul className="daylist">
          {wna.map((d) => (
            <li key={d.date.jdn}>
              <Link href={`/d/${d.date.jdn}/`} className="day-link">
                <span className="dd">{d.date.lunar.day}일 <span className="gj">{d.date.ganji.day}</span></span>
                <span className="ds">{solarLabel(d.date.solar, d.date.solar_calendar)}</span>
                <span className="dn">{d.articles.length}건</span>
              </Link>
              <ul className="titles">
                {d.articles.map((a) => (
                  <li key={a.id} className={a.summary ? "" : "raw"} lang={a.summary ? undefined : "zh-Hant"}>
                    {a.summary ? a.summary.title : Array.from(a.text.replace(/^○/, "")).slice(0, 40).join("") + "…"}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </section>

      {undated.length > 0 && (
        <section>
          <h2>선조실록 · 날 미상</h2>
          <ArticleList articles={undated} />
        </section>
      )}

      {wnb.length > 0 && (
        <section>
          <h2>선조수정실록 · 이 달</h2>
          <p className="meta">수정실록은 한 달 기사를 한 날에 몰아 적어서, 날짜가 아니라 달 단위로 보여 줍니다.</p>
          <ArticleList articles={wnb} />
        </section>
      )}
    </>
  );
}
