"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { type EventItem, type Index, type OtdItem, loadEvents, loadIndex, loadOtd, parseYmd, yearLabel } from "@/lib/data";

const DYNASTIES = ["고구려", "백제", "신라", "고려", "조선"];
const dynastyOf = (k: string) => DYNASTIES.find((d) => k.startsWith(d + " ")) ?? "조선";

function todayMd() {
  const d = new Date();
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function Home() {
  const router = useRouter();
  const [idx, setIdx] = useState<Index | null>(null);
  const [md, setMd] = useState(todayMd);
  const [otd, setOtd] = useState<OtdItem[] | null>(null);
  const [date, setDate] = useState("1592-05-23");
  const [err, setErr] = useState("");
  const [events, setEvents] = useState<EventItem[]>([]);

  useEffect(() => {
    loadIndex().then(setIdx).catch((e) => setErr(String(e)));
    loadEvents().then(setEvents).catch(() => setEvents([]));
  }, []);
  useEffect(() => {
    setOtd(null);
    loadOtd(md).then(setOtd).catch(() => setOtd([]));
  }, [md]);

  function go(e: React.FormEvent) {
    e.preventDefault();
    const m = /^(-?)(\d{1,4})-(\d{1,2})-(\d{1,2})$/.exec(date.trim());
    if (!m) return setErr("날짜를 1592-05-23처럼 적어 주세요 (기원전은 -57-04-15처럼)");
    const ym = `${m[1] ? "-" + m[2].padStart(3, "0") : m[2].padStart(4, "0")}-${m[3].padStart(2, "0")}`;
    router.push(`/view/?ym=${ym}&d=${Number(m[4])}`);
  }

  const [mm, dd] = md.split("-").map(Number);
  const books = idx?.books ?? {};
  return (
    <div className="home">
      {err && <p className="error">{err}</p>}
      {idx && (
        <p className="stats">
          기사 {idx.total.toLocaleString()}건 · 요약 {idx.summarized.toLocaleString()}건 · {idx.months.length.toLocaleString()}개월
        </p>
      )}

      <section className="panel">
        <h2>제목으로 찾기</h2>
        <form
          className="datejump"
          onSubmit={(e) => {
            e.preventDefault();
            const v = (e.currentTarget.elements.namedItem("q") as HTMLInputElement).value.trim();
            if (v) router.push(`/search/?q=${encodeURIComponent(v)}`);
          }}
        >
          <input name="q" placeholder="예: 이순신, 훈민정음, 거북선" aria-label="검색어" />
          <button type="submit">찾기</button>
        </form>
      </section>

      <section className="panel">
        <h2>날짜로 찾기</h2>
        <form onSubmit={go} className="datejump">
          <input value={date} onChange={(e) => setDate(e.target.value)} aria-label="양력 날짜" placeholder="1592-05-23" />
          <button type="submit">보기</button>
        </form>
        <p className="hint">양력 날짜 (1582년 10월 15일 이전은 율리우스력)</p>
      </section>

      {events.length > 0 && (
        <section className="panel">
          <h2>조선 주요 사건</h2>
          <p className="hint">사건 설명은 이 앱이 쓴 해설입니다(검수 전). 날짜는 실록 기사에 맞췄습니다.</p>
          <div className="eras">
            {Object.entries(
              events.reduce<Record<string, EventItem[]>>((acc, e) => {
                (acc[e.era] ??= []).push(e);
                return acc;
              }, {}),
            ).map(([era, list]) => (
              <div key={era} className="era">
                <h3>{era}</h3>
                <ul>
                  {list.map((e) => (
                    <li key={e.anchor + e.name}>
                      <Link href={`/view/?ym=${e.solar.slice(0, 7)}&d=${Number(e.solar.slice(8))}#ev`}>
                        <span className="ev-year">{parseYmd(e.solar)[0]}</span> {e.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel">
        <h2>왕별로 보기</h2>
        {DYNASTIES.map((dy) => {
          const ks = (idx?.kings ?? []).filter((k) => dynastyOf(k.king) === dy);
          if (!ks.length) return null;
          return (
            <div key={dy}>
              <h3 className="dynasty">{dy}</h3>
              <div className="kings">
                {ks.map((k) => (
                  <Link key={k.king} href={`/view/?ym=${k.first}`} className="king">
                    {dy === "조선" ? k.king : k.king.slice(dy.length + 1)}
                  </Link>
                ))}
              </div>
            </div>
          );
        })}
      </section>

      <section className="panel">
        <div className="otd-head">
          <h2>
            오늘의 실록 · {mm}월 {dd}일
          </h2>
          <input type="date" onChange={(e) => e.target.value && setMd(e.target.value.slice(5))} aria-label="월일 바꾸기" />
        </div>
        {!otd && <p className="hint">불러오는 중…</p>}
        {otd && otd.length === 0 && <p className="hint">이 날짜의 기사가 없습니다.</p>}
        {otd && otd.length > 0 && (
          <>
            <p className="hint">
              양력 {mm}월 {dd}일의 기사 {otd.length.toLocaleString()}건
            </p>
            <ul className="otd">
              {Object.entries(
                otd.reduce<Record<string, OtdItem[]>>((acc, it) => {
                  (acc[it.y] ??= []).push(it);
                  return acc;
                }, {}),
              ).map(([y, items]) => (
                <li key={y}>
                  <Link href={`/view/?ym=${y}-${String(mm).padStart(2, "0")}&d=${dd}`} className="otd-year">
                    {yearLabel(Number(y))}
                  </Link>
                  <span className="otd-titles">
                    {items.slice(0, 3).map((it) => (
                      <span key={it.id}>
                        {it.t}
                        <em> · {books[it.b] ?? it.b}</em>
                      </span>
                    ))}
                    {items.length > 3 && <span className="more">외 {items.length - 3}건</span>}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
