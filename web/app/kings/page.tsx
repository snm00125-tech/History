"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { type Index, type KingItem, loadIndex, loadKings } from "@/lib/data";

const Y0 = 1392;
const Y1 = 1911;
const pct = (y: number) => ((y - Y0) / (Y1 - Y0)) * 100;
const frac = (solar: string) => {
  const [y, m, d] = solar.split("-").map(Number);
  return y + (m - 1) / 12 + (d - 1) / 365;
};

function YearChart({ k, idx }: { k: KingItem; idx: Index | null }) {
  const [hover, setHover] = useState<string | null>(null);
  const entries = Object.entries(k.years);
  const max = Math.max(...entries.map(([, n]) => n), 1);
  const firstYm = (y: string) => idx?.months.find((m) => m.ym.startsWith(y))?.ym ?? `${y}-01`;
  const evYears = new Set(k.events.map((e) => e.solar.slice(0, 4)));
  return (
    <div className="ychart">
      <p className="hint ychart-read">
        {hover
          ? `${Number(hover)}년 · ${k.king}실록 기사 ${k.years[hover].toLocaleString()}건 — 누르면 그해로 갑니다`
          : `연도별 ${k.king}실록 기사 수 (가장 많은 해 ${max.toLocaleString()}건). 막대에 올리면 숫자가 보입니다.`}
      </p>
      <div className="ybars" role="list" onMouseLeave={() => setHover(null)}>
        {entries.map(([y, n]) => (
          <Link
            key={y}
            href={`/view/?ym=${firstYm(y)}`}
            className={`ybar${hover === y ? " on" : ""}`}
            role="listitem"
            aria-label={`${y}년 ${n}건`}
            onMouseEnter={() => setHover(y)}
            onFocus={() => setHover(y)}
          >
            <span className="ybar-fill" style={{ height: `${Math.max(3, (n / max) * 100)}%` }} />
            {evYears.has(y) && <span className="ybar-ev">★</span>}
          </Link>
        ))}
      </div>
      <div className="ybars-axis">
        <span>{Number(entries[0][0])}</span>
        <span>{Number(entries[entries.length - 1][0])}</span>
      </div>
    </div>
  );
}

export default function KingsPage() {
  const [kings, setKings] = useState<KingItem[]>([]);
  const [idx, setIdx] = useState<Index | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    loadKings().then(setKings);
    loadIndex().then(setIdx);
  }, []);
  const ticks = useMemo(() => [1400, 1500, 1600, 1700, 1800, 1900], []);

  return (
    <div className="kingsview">
      <h2>왕별 연표</h2>
      <p className="hint">
        막대 = 그 왕 실록의 첫 기사부터 마지막 기사까지(양력). 왕을 누르면 연도별 기사 수와 그 시기 주요 사건이 나옵니다.
      </p>
      <div className="kaxis" aria-hidden>
        {ticks.map((t) => (
          <span key={t} style={{ left: `${pct(t)}%` }}>
            {t}
          </span>
        ))}
      </div>
      <ul className="klist">
        {kings.map((k) => {
          const a = frac(k.start);
          const b = frac(k.end);
          const yrs = Math.max(1, Math.round(b - a));
          const isOpen = open === k.king;
          return (
            <li key={k.king} className={isOpen ? "open" : ""}>
              <button className="krow" onClick={() => setOpen(isOpen ? null : k.king)} aria-expanded={isOpen}>
                <span className="kname">{k.king}</span>
                <span className="ktrack">
                  <span className="kbar" style={{ left: `${pct(a)}%`, width: `${Math.max(0.4, pct(b) - pct(a))}%` }} />
                </span>
                <span className="kmeta">
                  {Math.floor(a)}–{Math.floor(b)}
                  <span className="kdur"> · 약 {yrs}년</span>
                </span>
              </button>
              {isOpen && (
                <div className="kdetail">
                  <p>
                    {k.start} ~ {k.end} · 실록 기사 {k.articles.toLocaleString()}건 ·{" "}
                    <Link href={`/view/?ym=${k.start.slice(0, 7)}&d=${Number(k.start.slice(8))}`}>첫 기사 날로 →</Link>
                  </p>
                  <YearChart k={k} idx={idx} />
                  {k.events.length > 0 && (
                    <ul className="kevents">
                      {k.events.map((e) => (
                        <li key={e.name}>
                          <Link href={`/view/?ym=${e.solar.slice(0, 7)}&d=${Number(e.solar.slice(8))}`}>
                            ★ {e.solar.replaceAll("-", ".")} {e.name}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
