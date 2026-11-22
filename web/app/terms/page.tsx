"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { type Term, loadTerms } from "@/lib/data";

export default function TermsPage() {
  const [terms, setTerms] = useState<Term[]>([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  useEffect(() => {
    loadTerms().then(setTerms);
  }, []);
  const cats = useMemo(() => [...new Set(terms.map((t) => t.c))], [terms]);
  const shown = terms.filter(
    (t) => (!cat || t.c === cat) && (!q || t.t.includes(q) || t.h.includes(q) || t.d.includes(q)),
  );
  return (
    <div className="termsview">
      <h2>용어 사전</h2>
      <p className="hint">
        실록 제목에 자주 나오는 관청·관직·제도 용어 {terms.length}개. 이 앱이 쓴 풀이입니다(검수 전). 기사를 펼치면 그 기사
        제목에 나온 용어 풀이가 함께 보입니다.
      </p>
      <div className="datejump">
        <input id="termq" value={q} onChange={(e) => setQ(e.target.value)} placeholder="예: 승지, 비변사, 가자" aria-label="용어 찾기" />
      </div>
      <div className="filters" style={{ marginTop: 10 }}>
        <button className={!cat ? "on" : ""} onClick={() => setCat(null)}>
          전체
        </button>
        {cats.map((c) => (
          <button key={c} className={cat === c ? "on" : ""} onClick={() => setCat(c)}>
            {c}
          </button>
        ))}
      </div>
      <dl className="termlist">
        {shown.map((t) => (
          <div key={t.t}>
            <dt>
              {t.t} <span className="hj">{t.h}</span> <span className="chip">{t.c}</span>
            </dt>
            <dd>
              {t.d}{" "}
              <Link href={`/search/?q=${encodeURIComponent(t.t)}`} className="hint">
                이 말이 나오는 기사 →
              </Link>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
