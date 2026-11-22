"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { type Index, loadIndex } from "@/lib/data";
import { type PersonHit, findPersons } from "@/lib/person";
import { type Doc, candidates, verify } from "@/lib/search";

const PAGE = 100;

function SearchInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const q = sp.get("q") ?? "";
  const [input, setInput] = useState(q);
  const [idx, setIdx] = useState<Index | null>(null);
  const [ids, setIds] = useState<number[] | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [next, setNext] = useState(0);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [bookFilter, setBookFilter] = useState<string | null>(null);
  const [people, setPeople] = useState<PersonHit[]>([]);

  useEffect(() => {
    loadIndex().then(setIdx);
  }, []);
  useEffect(() => {
    setInput(q);
    setIds(null);
    setDocs([]);
    setMsg("");
    setBookFilter(null);
    setPeople([]);
    if (!q) return;
    findPersons(q, 12).then(setPeople);
    let live = true;
    setBusy(true);
    (async () => {
      const c = await candidates(q);
      if (!live) return;
      if ("error" in c) {
        setMsg(c.error);
        setBusy(false);
        return;
      }
      setIds(c.ids);
      const r = await verify(q, c.ids, 0, PAGE);
      if (!live) return;
      setDocs(r.docs);
      setNext(r.next);
      setBusy(false);
    })();
    return () => {
      live = false;
    };
  }, [q]);

  async function more() {
    if (!ids) return;
    setBusy(true);
    const r = await verify(q, ids, next, PAGE);
    setDocs((d) => [...d, ...r.docs]);
    setNext(r.next);
    setBusy(false);
  }

  const books = idx?.books ?? {};
  const shown = docs.filter((d) => !bookFilter || d[3] === bookFilter);
  const bookCounts = docs.reduce<Record<string, number>>((a, d) => ((a[d[3]] = (a[d[3]] ?? 0) + 1), a), {});

  return (
    <div className="searchview">
      <form
        className="datejump"
        onSubmit={(e) => {
          e.preventDefault();
          router.push(`/search/?q=${encodeURIComponent(input.trim())}`);
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="예: 이순신, 훈민정음, 거북선 (인물·기사 제목)" aria-label="검색어" />
        <button type="submit">찾기</button>
      </form>
      <p className="hint">기사 제목(국편 국문 제목·비변사등록 제목·일기 첫머리)에서 찾습니다. 날짜순으로 보여 줍니다.</p>
      {people.length > 0 && (
        <section className="panel">
          <h3 className="ptitle">인물</h3>
          <ul className="plist">
            {people.map(([pid, ko, hj, born, died, kind, n]) => (
              <li key={pid}>
                <Link href={`/person/?id=${pid}`}>
                  <strong>{ko}</strong> <span className="hj">{hj}</span>
                  <span className="pmeta">
                    {born || died ? ` ${born ?? "?"}~${died ?? "?"}` : ""}
                    {kind ? ` · ${kind}` : ""} · 기사 {n.toLocaleString()}건
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
      {msg && <p className="error">{msg}</p>}
      {busy && <p className="hint">찾는 중…</p>}
      {ids && !busy && (
        <p className="stats">
          「{q}」 후보 {ids.length.toLocaleString()}건 중 {docs.length.toLocaleString()}건 표시
          {next < ids.length && " (더 있음)"}
        </p>
      )}
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
      <ul className="results">
        {shown.map(([t, solar, id, b]) => (
          <li key={id}>
            {solar ? (
              <Link href={`/view/?ym=${solar.slice(0, 7)}&d=${Number(solar.slice(8))}#${id}`}>
                <span className="r-date">{solar.replaceAll("-", ".")}</span>
                <span className="r-title">{t}</span>
              </Link>
            ) : (
              <span>
                <span className="r-date">날짜 없음</span>
                <span className="r-title">{t}</span>
              </span>
            )}
            <span className="r-book">{books[b] ?? b}</span>
          </li>
        ))}
      </ul>
      {ids && next < ids.length && !busy && (
        <button className="morebtn" onClick={more}>
          더 보기
        </button>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<p className="hint">불러오는 중…</p>}>
      <SearchInner />
    </Suspense>
  );
}
