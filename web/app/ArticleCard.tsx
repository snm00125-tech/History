"use client";

import { useEffect, useRef, useState } from "react";
import { type Article, REVIEW_LABEL, sourceSite, sourceUrl } from "@/lib/data";

export function ArticleCard({
  a,
  books,
  groups,
  focus = false,
}: {
  a: Article;
  books: Record<string, string>;
  groups: Record<string, string>;
  focus?: boolean; // 주소 #기사ID로 들어오면 펼치고 화면으로 가져온다
}) {
  const [open, setOpen] = useState(focus);
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (focus) {
      setOpen(true);
      ref.current?.scrollIntoView({ block: "start" });
    }
  }, [focus]);
  return (
    <article ref={ref} className={`card${open ? " open" : ""}${focus ? " focus" : ""}`} id={a.id}>
      <button className="card-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="card-title">{a.t || a.s?.title || "(제목 없음)"}</span>
        <span className="card-meta">
          <span className="book">{books[a.b] ?? a.b}</span>
          {a.reg && <span className="book">{a.reg}</span>}
          {a.g.map((g) => (
            <span key={g} className={`chip g-${g}`}>
              {groups[g] ?? g}
            </span>
          ))}
          {a.s && <span className="chip sum">요약</span>}
          {a.r && <span className="chip warn">{REVIEW_LABEL[a.r] ?? a.r}</span>}
        </span>
      </button>
      {open && (
        <div className="card-body">
          {a.s && (
            <section className="summary">
              <h4>요약 · {a.s.title}</h4>
              <ul>
                {a.s.sentences.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
              {a.s.commentary.length > 0 && (
                <div className="commentary">
                  {a.s.commentary.map((c, i) => (
                    <p key={i}>해설: {c}</p>
                  ))}
                </div>
              )}
            </section>
          )}
          <section className="source">
            <h4>원문</h4>
            <p className="hanmun">{a.x}</p>
          </section>
          <a className="ext" href={sourceUrl(a.id)} target="_blank" rel="noreferrer">
            {sourceSite(a.id)}에서 보기 ↗
          </a>
        </div>
      )}
    </article>
  );
}
