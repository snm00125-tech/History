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

export default function PersonPage() {
  return (
    <Suspense fallback={<p className="hint">불러오는 중…</p>}>
      <PersonInner />
    </Suspense>
  );
}
