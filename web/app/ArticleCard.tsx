"use client";

import { useState } from "react";
import { type Article, REVIEW_LABEL, sillokUrl } from "@/lib/data";

export function ArticleCard({
  a,
  books,
  groups,
}: {
  a: Article;
  books: Record<string, string>;
  groups: Record<string, string>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <article className={`card${open ? " open" : ""}`} id={a.id}>
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
          <a className="ext" href={sillokUrl(a.id)} target="_blank" rel="noreferrer">
            국사편찬위원회 실록 사이트에서 번역 보기 ↗
          </a>
        </div>
      )}
    </article>
  );
}
