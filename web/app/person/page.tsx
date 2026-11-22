"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { type Index, loadIndex } from "@/lib/data";
import { type Person, decodeDocs, loadPerson } from "@/lib/person";
import { type Doc, docsByIds } from "@/lib/search";

const PAGE = 100;

function PersonInner() {
  const id = useSearchParams().get("id") ?? "";
  const [p, setP] = useState<Person | null | undefined>(undefined);
  const [idx, setIdx] = useState<Index | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [shown, setShown] = useState(0);
  const [showOff, setShowOff] = useState(false);
  const ids = useMemo(() => (p ? decodeDocs(p.docs) : []), [p]);

  useEffect(() => {
    loadIndex().then(setIdx);
  }, []);
  useEffect(() => {
    setP(undefined);
    setDocs([]);
    setShown(0);
    if (id) loadPerson(id).then(setP);
  }, [id]);
  useEffect(() => {
    if (!ids.length) return;
    docsByIds(ids.slice(0, PAGE)).then((d) => {
      setDocs(d);
      setShown(Math.min(PAGE, ids.length));
    });
  }, [ids]);

  async function more() {
    const next = ids.slice(shown, shown + PAGE);
    const d = await docsByIds(next);
    setDocs((x) => [...x, ...d]);
    setShown(shown + next.length);
  }

  if (p === undefined) return <p className="hint">불러오는 중…</p>;
  if (p === null) return <p className="error">인물을 찾지 못했습니다.</p>;
  const books = idx?.books ?? {};
  const years = docs.length ? `${docs[0][1].slice(0, 4)}~${docs[docs.length - 1][1].slice(0, 4)}` : "";
  const facts = [
    p.born || p.died ? `${p.born ?? "?"}~${p.died ?? "?"}` : null,
    p.bon && `본관 ${p.bon}`,
    p.ja && `자 ${p.ja}`,
    p.ho && `호 ${p.ho}`,
    p.siho && `시호 ${p.siho}`,
    p.kind,
  ].filter(Boolean);

  return (
    <div className="personview">
      <h2>
        {p.ko} <span className="hj">{p.hj}</span>
      </h2>
      <p className="facts">{facts.join(" · ")}</p>
      <p className="hint">
        실록 원문 인명 색인 기준 기사 {ids.length.toLocaleString()}건{years && ` (보이는 범위 ${years})`}. 인물 정보:
        국사편찬위원회 실록 부가정보.
      </p>

      {p.wiki && (p.wiki.summary || p.wiki.img) && (
        <section className="panel pwiki">
          {p.wiki.img && (
            <figure>
              <a href={p.wiki.img.page} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={p.wiki.img.thumb} alt={`${p.ko} 그림`} loading="lazy" />
              </a>
              <figcaption>
                {p.wiki.img.artist && `${p.wiki.img.artist} · `}
                {p.wiki.img.license || "저작권 정보 없음"} ·{" "}
                <a href={p.wiki.img.page} target="_blank" rel="noreferrer">
                  위키미디어 공용
                </a>
              </figcaption>
            </figure>
          )}
          <div>
            <h3>위키백과 요약</h3>
            {p.wiki.summary ? <p>{p.wiki.summary}</p> : <p className="hint">요약 없음</p>}
            <p className="hint">
              출처:{" "}
              {p.wiki.url ? (
                <a href={p.wiki.url} target="_blank" rel="noreferrer">
                  한국어 위키백과 「{p.wiki.title}」
                </a>
              ) : (
                "위키데이터"
              )}{" "}
              (CC BY-SA 4.0) · 국편 인물과 이름+{p.wiki.match}으로 이었습니다(이 앱 해설 아님) ·{" "}
              <a href={`https://www.wikidata.org/wiki/${p.wiki.qid}`} target="_blank" rel="noreferrer">
                위키데이터
              </a>
            </p>
          </div>
        </section>
      )}

      {p.yc && Object.keys(p.yc).length > 1 && <YearBars yc={p.yc} />}

      {p.co && p.co.length > 0 && (
        <section className="panel">
          <h3>같은 기사에 자주 함께 나오는 인물</h3>
          <p className="cops">
            {p.co.map(([qid, ko, n]) => (
              <Link key={qid} href={`/person/?id=${qid}`}>
                {ko} <small>{n}</small>
              </Link>
            ))}
          </p>
          <p className="hint">원문 인명 색인에서 같은 기사에 함께 이름이 나온 횟수입니다(관계의 성격은 기사에서 확인).</p>
        </section>
      )}

      {p.off.length > 0 && (
        <section className="panel">
          <button className="linkbtn" onClick={() => setShowOff(!showOff)}>
            관직 기록 {p.off.length}건 {showOff ? "접기 ▲" : "펼치기 ▼"}
          </button>
          {showOff && (
            <ul className="offlist">
              {p.off.map(([solar, office, status], i) => (
                <li key={i}>
                  <span className="r-date">{solar.replaceAll("-", ".")}</span> {office}
                  {status && status !== "현직" && <em> ({status})</em>}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <h3>나오는 기사 (날짜순)</h3>
      <ul className="results">
        {docs.map(([t, solar, aid, b]) => (
          <li key={aid}>
            {solar ? (
              <Link href={`/view/?ym=${solar.slice(0, 7)}&d=${Number(solar.slice(8))}#${aid}`}>
                <span className="r-date">{solar.replaceAll("-", ".")}</span>
                <span className="r-title">{t}</span>
              </Link>
            ) : (
              <span className="r-title">{t}</span>
            )}
            <span className="r-book">{books[b] ?? b}</span>
          </li>
        ))}
      </ul>
      {shown < ids.length && (
        <button className="morebtn" onClick={more}>
          더 보기 ({(ids.length - shown).toLocaleString()}건 남음)
        </button>
      )}
    </div>
  );
}

/** 연도별 기사 수 막대 (한 계열, 막대에 마우스를 올리면 수) */
function YearBars({ yc }: { yc: Record<string, number> }) {
  const ys = Object.keys(yc).map(Number);
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);
  const max = Math.max(...Object.values(yc));
  const n = y1 - y0 + 1;
  const W = 640;
  const H = 90;
  const bw = W / n;
  const [hov, setHov] = useState<number | null>(null);
  return (
    <section className="panel">
      <h3>
        연도별 기사 수 <small className="hint">({y0}~{y1}년, 가장 많은 해 {max}건)</small>
      </h3>
      <div className="ybars">
        <svg viewBox={`0 0 ${W} ${H + 16}`} preserveAspectRatio="none" role="img" aria-label="연도별 기사 수">
          {Object.entries(yc).map(([y, c]) => {
            const x = (Number(y) - y0) * bw;
            const h = Math.max(1, (c / max) * H);
            return (
              <rect key={y} x={x + 0.5} y={H - h} width={Math.max(1, bw - 1)} height={h} rx={bw > 6 ? 2 : 0}
                className={hov === Number(y) ? "yb on" : "yb"}
                onPointerEnter={() => setHov(Number(y))} onPointerLeave={() => setHov(null)} />
            );
          })}
          <line x1={0} x2={W} y1={H} y2={H} className="yb-base" />
        </svg>
        <p className="hint">{hov != null ? `${hov}년 · ${yc[hov]}건` : "막대에 마우스를 올리면 그해 기사 수"}</p>
      </div>
    </section>
  );
}

export default function PersonPage() {
  return (
    <Suspense fallback={<p className="hint">불러오는 중…</p>}>
      <PersonInner />
    </Suspense>
  );
}
