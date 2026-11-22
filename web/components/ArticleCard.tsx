"use client";

import { useMemo, useState } from "react";
import type { Article } from "@/lib/types";
import { BOOK_NAMES, GROUP_NAMES, STATUS_NOTE } from "@/lib/format";

type Seg = { text: string; cls: string[]; ev: boolean };

/** 원문을 주석·근거 구간 경계로 자른다. 오프셋은 코드포인트 기준(파이썬과 같음). */
function segments(text: string, notes: Article["notes"], evidence: [number, number][]): Seg[] {
  const chars = Array.from(text);
  const cuts = new Set<number>([0, chars.length]);
  for (const [, s, e] of notes) { cuts.add(s); cuts.add(e); }
  for (const [s, e] of evidence) { cuts.add(s); cuts.add(e); }
  const pts = [...cuts].filter((x) => x >= 0 && x <= chars.length).sort((a, b) => a - b);
  const out: Seg[] = [];
  for (let i = 0; i + 1 < pts.length; i++) {
    const s = pts[i], e = pts[i + 1];
    if (s === e) continue;
    const cls: string[] = [];
    for (const [k, ns, ne] of notes) if (ns <= s && e <= ne) cls.push(`n-${k}`);
    const ev = evidence.some(([es, ee]) => es <= s && e <= ee);
    out.push({ text: chars.slice(s, e).join(""), cls, ev });
  }
  return out;
}

export default function ArticleCard({ a, defaultOpen = false }: { a: Article; defaultOpen?: boolean }) {
  const [sel, setSel] = useState<number | null>(null);
  const [open, setOpen] = useState(defaultOpen || !a.summary);
  const evidence = useMemo<[number, number][]>(() => {
    if (!a.summary) return [];
    if (sel === null) return a.summary.sentences.flatMap((s) => s.evidence);
    return a.summary.sentences[sel]?.evidence ?? [];
  }, [a.summary, sel]);
  const segs = useMemo(() => segments(a.text, a.notes, open ? evidence : []), [a, evidence, open]);
  const hasSaron = a.notes.some(([k]) => k === "사론");

  return (
    <article className={`card book-${a.book}`} id={a.id}>
      <header className="card-head">
        <span className="book">{BOOK_NAMES[a.book] ?? a.book}</span>
        {a.groups.map((g) => (
          <span key={g} className={`tag g-${g}`}>{GROUP_NAMES[g] ?? g}</span>
        ))}
        {hasSaron && <span className="tag saron">사론</span>}
        {a.needs_review && STATUS_NOTE[a.jdn_status] && (
          <span className="tag warn" title={STATUS_NOTE[a.jdn_status]}>날짜 검수</span>
        )}
      </header>

      {a.summary ? (
        <>
          <h3 className="title">{a.summary.title}</h3>
          <ol className="sents">
            {a.summary.sentences.map((s, i) => (
              <li key={i}>
                <button
                  type="button"
                  className={`sent${sel === i ? " on" : ""}`}
                  onClick={() => { setSel(sel === i ? null : i); setOpen(true); }}
                  title="원문에서 근거 구절 보기"
                >
                  {s.text}
                </button>
              </li>
            ))}
          </ol>
          {a.summary.commentary.length > 0 && (
            <div className="comment">
              <span className="comment-label">해설</span>
              {a.summary.commentary.map((c, i) => (
                <p key={i}>{c.text}{!c.verified && <span className="unverified"> · 검수 전</span>}</p>
              ))}
            </div>
          )}
          <p className="meta">자체 요약 · {a.summary.review_status === "approved" ? "검수 완료" : "검수 전"} · 문장을 누르면 원문 근거가 표시됩니다</p>
        </>
      ) : (
        <p className="pending">아직 요약이 없습니다. 원문을 먼저 싣습니다.</p>
      )}

      {a.needs_review && STATUS_NOTE[a.jdn_status] && <p className="meta warn-text">{STATUS_NOTE[a.jdn_status]}</p>}

      <div className="src">
        <button type="button" className="toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "원문 접기" : "원문 보기"}
        </button>
        <a className="ext" href={a.url} target="_blank" rel="noopener noreferrer">
          국사편찬위원회 원문 ↗
        </a>
      </div>
      {open && (
        <div className="hanmun" lang="zh-Hant">
          {segs.map((s, i) => (
            <span key={i} className={[...s.cls, s.ev ? "ev" : ""].join(" ").trim() || undefined}>{s.text}</span>
          ))}
          <p className="pages">{a.sources.map((s) => s.join(" ")).join(" · ")}</p>
        </div>
      )}
    </article>
  );
}
