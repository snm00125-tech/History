import type { Metadata } from "next";
import Link from "next/link";
import { getDays, getIndex, neighborDays } from "@/lib/data";
import { fullDate, lunarMonthLabel } from "@/lib/format";
import ArticleList from "@/components/ArticleList";

type P = { params: Promise<{ jdn: string }> };

export function generateStaticParams() {
  return [...getDays().keys()].map((j) => ({ jdn: String(j) }));
}

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const d = getDays().get(Number((await params).jdn))!;
  const f = fullDate(d.date);
  return { title: `${f.solar} · ${f.lunar}` };
}

export default async function DayPage({ params }: P) {
  const jdn = Number((await params).jdn);
  const d = getDays().get(jdn)!;
  const f = fullDate(d.date);
  const { prev, next } = neighborDays(jdn);
  const months = getIndex().months.filter((m) => d.monthKeys.includes(m.key));

  return (
    <>
      <nav className="crumbs">
        <Link href="/">전체</Link>
        {months.map((m) => (
          <Link key={m.key} href={`/m/${m.key}/`}>{m.lunar.year}년 {lunarMonthLabel(m.lunar)}{m.n_month > 0 ? ` (수정실록 ${m.n_month}건)` : ""}</Link>
        ))}
        {prev && <Link href={`/d/${prev}/`}>← 전날 기록</Link>}
        {next && <Link href={`/d/${next}/`}>다음 기록 →</Link>}
      </nav>
      <section className="date-head">
        <h1>{f.solar}</h1>
        <dl className="dates">
          <div><dt>음력</dt><dd>{f.lunar.replace("음력 ", "")}</dd></div>
          <div><dt>왕력</dt><dd>{f.regnal}</dd></div>
          <div><dt>간지</dt><dd>{f.ganji}</dd></div>
          <div><dt>율리우스적일</dt><dd>{jdn}</dd></div>
        </dl>
      </section>
      <ArticleList articles={d.articles} />
    </>
  );
}
