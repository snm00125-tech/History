"use client";

// 연도별 도식: 왕조 띠 · 왕 막대 · 사건 ★ · 연도별 기록 수(자료별 누적 막대). 끌기·휠로 확대.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { type Index, loadIndex, parseYmd, yearLabel, ymKey } from "@/lib/data";

type Timeline = {
  years: [number, number];
  series: { key: string; name: string }[];
  counts: number[][];
  groups: Record<string, number[]>;
  dynasties: { name: string; lane: number; start: number; end: number; note?: string }[];
  kings: { dyn: string; name: string; start: number; end: number }[];
  events: { name: string; solar: string; src: "app" | "th" }[];
};

const PRESETS: [string, number, number][] = [
  ["전체", -720, 2010],
  ["삼국", -60, 940],
  ["고려", 910, 1400],
  ["조선", 1385, 1915],
  ["임진왜란", 1588, 1602],
  ["근현대", 1860, 2010],
];
const BIN_STEPS = [1, 2, 5, 10, 20, 25, 50, 100];
const H = { lanes: 3 * 20, kings: 22, events: 22, bars: 220, axis: 26 };

/** 역사 연도(0년 없음) ↔ 연속 축 값 */
const toAxis = (y: number) => (y < 0 ? y + 1 : y);
const fromAxis = (a: number) => (a <= 0 ? a - 1 : a);

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

export default function TimelinePage() {
  const router = useRouter();
  const [tl, setTl] = useState<Timeline | null>(null);
  const [idx, setIdx] = useState<Index | null>(null);
  const [err, setErr] = useState("");
  const [view, setView] = useState<[number, number]>([toAxis(-720), toAxis(2010)]);
  const [group, setGroup] = useState<string | null>(null);
  const [hover, setHover] = useState<{ x: number; bin: number } | null>(null);
  const [evHover, setEvHover] = useState<{ x: number; i: number } | null>(null);
  const [table, setTable] = useState(false);
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(900);
  const drag = useRef<{ x: number; v: [number, number] } | null>(null);

  useEffect(() => {
    fetch("/data/timeline.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setTl)
      .catch((e) => setErr(`연도 자료를 못 읽었습니다 (${e})`));
    loadIndex().then(setIdx).catch(() => {});
  }, []);
  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(320, e.contentRect.width)));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, [tl]); // 자료를 읽은 뒤에야 상자가 그려진다

  const [a0, a1] = view;
  const px = (a: number) => ((a - a0) / (a1 - a0)) * width;
  const axisOfPx = (x: number) => a0 + (x / width) * (a1 - a0);

  // 막대 묶음: 막대 하나가 최소 4px
  const bin = useMemo(() => {
    const per = (a1 - a0) / (width / 4);
    return BIN_STEPS.find((b) => b >= per) ?? 100;
  }, [a0, a1, width]);

  const bins = useMemo(() => {
    if (!tl) return [];
    const [y0, y1] = tl.years;
    const first = toAxis(y0);
    const ser = group ? [tl.groups[group] ?? []] : tl.counts;
    const out: { a: number; vals: number[]; total: number }[] = [];
    const start = Math.floor(Math.max(a0, first) / bin) * bin;
    const end = Math.min(a1, toAxis(y1) + 1);
    for (let a = start; a < end; a += bin) {
      const vals = ser.map((s) => {
        let t = 0;
        for (let k = a; k < a + bin; k++) {
          const i = k - first;
          if (i >= 0 && i < s.length) t += s[i];
        }
        return t;
      });
      const shown = vals.map((v, i) => (!group && hidden.has(i) ? 0 : v));
      out.push({ a, vals: shown, total: shown.reduce((x, y) => x + y, 0) });
    }
    return out;
  }, [tl, a0, a1, bin, group, hidden]);
  const yMax = niceMax(Math.max(1, ...bins.map((b) => b.total)));

  function zoom(factor: number, centerPx: number) {
    const c = axisOfPx(centerPx);
    let n0 = c - (c - a0) * factor;
    let n1 = c + (a1 - c) * factor;
    if (n1 - n0 < 8) return;
    const lo = toAxis(-760);
    const hi = toAxis(2020);
    if (n1 - n0 > hi - lo) [n0, n1] = [lo, hi];
    setView([Math.max(lo, n0), Math.min(hi, n1)]);
  }
  const svgRef = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoom(e.deltaY > 0 ? 1.2 : 1 / 1.2, e.clientX - r.left);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  const goYear = (y: number) => {
    const key = y * 100 + 1;
    const m = idx?.months.find((x) => ymKey(x.ym) >= key);
    if (m) router.push(`/view/?ym=${m.ym}`);
  };

  const evs = useMemo(
    () =>
      (tl?.events ?? [])
        .map((e) => ({ ...e, a: toAxis(parseYmd(e.solar)[0]) + (parseYmd(e.solar)[1] - 1) / 12 }))
        .filter((e) => e.a >= a0 && e.a <= a1)
        .sort((x, y) => (x.src === y.src ? 0 : x.src === "app" ? -1 : 1))
        .reduce<{ out: (Timeline["events"][number] & { a: number })[]; xs: number[] }>(
          (acc, e) => {
            const x = ((e.a - a0) / (a1 - a0)) * width;
            if (acc.xs.every((p) => Math.abs(p - x) >= 14)) {
              acc.out.push(e);
              acc.xs.push(x);
            }
            return acc;
          },
          { out: [], xs: [] },
        ).out,
    [tl, a0, a1, width],
  );
  const showKings = a1 - a0 <= 420;
  const kings = (tl?.kings ?? []).filter((k) => toAxis(k.end) + 1 >= a0 && toAxis(k.start) <= a1);
  const top = { lanes: 0, kings: H.lanes, events: H.lanes + (showKings ? H.kings : 0) };
  const barsTop = top.events + H.events;
  const totalH = barsTop + H.bars + H.axis;

  // 눈금
  const ticks = useMemo(() => {
    const span = a1 - a0;
    const step = [1, 2, 5, 10, 20, 50, 100, 200, 500].find((s) => span / s <= width / 70) ?? 500;
    const out: number[] = [];
    for (let a = Math.ceil(a0 / step) * step; a <= a1; a += step) out.push(a);
    return out;
  }, [a0, a1, width]);

  const hb = hover ? bins[hover.bin] : null;
  const binLabel = (a: number) =>
    bin === 1 ? yearLabel(fromAxis(a)) : `${yearLabel(fromAxis(a))}~${yearLabel(fromAxis(a + bin - 1))}`;
  const whoAt = (a: number) => {
    const y = fromAxis(a);
    const ds = (tl?.dynasties ?? []).filter((d) => d.start <= y && y < d.end).map((d) => d.name);
    const ks = (tl?.kings ?? []).filter((k) => k.start <= y && y <= k.end).map((k) => `${k.dyn} ${k.name}`);
    return { ds, ks };
  };

  if (err) return <p className="error">{err}</p>;
  if (!tl) return <p className="hint">불러오는 중…</p>;
  const series = group ? [{ key: group, name: idx?.groups[group] ?? group }] : tl.series;

  return (
    <div className="tl">
      <h1>연도별로 보기</h1>
      <p className="hint">
        휠(또는 아래 단추)로 확대·축소, 끌어서 옮기기. 막대를 누르면 그해 기록으로 갑니다. 막대 하나 ={" "}
        {bin === 1 ? "1년" : `${bin}년`}.
      </p>

      <div className="filters">
        {PRESETS.map(([n, s, e]) => (
          <button key={n} onClick={() => setView([toAxis(s), toAxis(e)])}>
            {n}
          </button>
        ))}
        <button onClick={() => zoom(1 / 1.6, width / 2)} aria-label="확대">
          ＋
        </button>
        <button onClick={() => zoom(1.6, width / 2)} aria-label="축소">
          －
        </button>
      </div>
      <div className="filters">
        <button className={!group ? "on" : ""} onClick={() => setGroup(null)}>
          자료별
        </button>
        {Object.entries(idx?.groups ?? {}).map(([g, n]) => (
          <button key={g} className={group === g ? "on" : ""} onClick={() => setGroup(g)}>
            {n}
          </button>
        ))}
        <button className={table ? "on" : ""} onClick={() => setTable((t) => !t)}>
          표로 보기
        </button>
      </div>

      <div className="tl-legend">
        {series.map((s, i) => (
          <button
            key={s.key}
            className={!group && hidden.has(i) ? "off" : ""}
            disabled={!!group}
            title={group ? "" : "누르면 이 자료를 숨기거나 다시 보입니다"}
            onClick={() =>
              setHidden((h) => {
                const n = new Set(h);
                if (n.has(i)) n.delete(i);
                else n.add(i);
                return n;
              })
            }
          >
            <i style={{ background: `var(--s${group ? 1 : i + 1})` }} />
            {s.name}
          </button>
        ))}
        {!group && <small>(눌러서 숨기기 — 승정원일기를 숨기면 다른 시대가 잘 보입니다)</small>}
      </div>

      <div className="tl-wrap" ref={wrap}>
        <svg
          ref={svgRef}
          width={width}
          height={totalH}
          className="tl-svg"
          onPointerDown={(e) => {
            drag.current = { x: e.clientX, v: view };
            (e.target as Element).setPointerCapture?.(e.pointerId);
          }}
          onPointerMove={(e) => {
            const r = svgRef.current!.getBoundingClientRect();
            const x = e.clientX - r.left;
            if (drag.current && Math.abs(e.clientX - drag.current.x) > 3) {
              const d = ((e.clientX - drag.current.x) / width) * (drag.current.v[1] - drag.current.v[0]);
              setView([drag.current.v[0] - d, drag.current.v[1] - d]);
              setHover(null);
              return;
            }
            const y = e.clientY - r.top;
            if (y >= barsTop && y <= barsTop + H.bars) {
              const a = axisOfPx(x);
              const i = bins.findIndex((b) => a >= b.a && a < b.a + bin);
              setHover(i >= 0 ? { x, bin: i } : null);
            } else setHover(null);
          }}
          onPointerUp={(e) => {
            const moved = drag.current && Math.abs(e.clientX - drag.current.x) > 3;
            drag.current = null;
            if (!moved && hover && hb && hb.total > 0) goYear(fromAxis(hb.a));
          }}
          onPointerLeave={() => {
            drag.current = null;
            setHover(null);
          }}
        >
          {/* 왕조 띠 */}
          {tl.dynasties.map((d) => {
            const x0 = Math.max(0, px(toAxis(d.start)));
            const x1 = Math.min(width, px(toAxis(d.end)));
            if (x1 <= 0 || x0 >= width) return null;
            const y = top.lanes + d.lane * 20;
            return (
              <g key={d.name}>
                <rect x={x0} y={y + 2} width={Math.max(1, x1 - x0 - 2)} height={16} rx={4} className="tl-dyn" />
                {x1 - x0 > 40 && (
                  <text x={x0 + 6} y={y + 14} className="tl-dyn-t">
                    {d.name}
                  </text>
                )}
              </g>
            );
          })}
          {/* 왕 */}
          {showKings &&
            kings.map((k, i) => {
              const x0 = Math.max(0, px(toAxis(k.start)));
              const x1 = Math.min(width, px(toAxis(k.end) + 1));
              return (
                <g key={`${k.dyn}${k.name}`}>
                  <rect x={x0} y={top.kings + 3} width={Math.max(1, x1 - x0 - 2)} height={16} rx={4}
                    className={i % 2 ? "tl-king b" : "tl-king"}>
                    <title>{`${k.dyn} ${k.name} (${yearLabel(k.start)}~${yearLabel(k.end)}, 기록 기준)`}</title>
                  </rect>
                  {x1 - x0 > 34 && (
                    <text x={x0 + 4} y={top.kings + 15} className="tl-king-t">
                      {k.name}
                    </text>
                  )}
                </g>
              );
            })}
          {/* 사건 */}
          {evs.map((e, i) => (
            <text key={i} x={px(e.a)} y={top.events + 16} className={e.src === "app" ? "tl-ev app" : "tl-ev"}
              textAnchor="middle"
              onPointerEnter={() => setEvHover({ x: px(e.a), i })}
              onPointerLeave={() => setEvHover(null)}
              onClick={() => {
                const [y, m, d] = parseYmd(e.solar);
                const ym = `${e.solar.slice(0, e.solar.length - 6)}-${String(m).padStart(2, "0")}`;
                router.push(`/view/?ym=${ym}&d=${d}`);
                void y;
              }}>
              ★
            </text>
          ))}
          {/* 막대 */}
          <line x1={0} x2={width} y1={barsTop + H.bars} y2={barsTop + H.bars} className="tl-base" />
          {[0.5, 1].map((f) => (
            <g key={f}>
              <line x1={0} x2={width} y1={barsTop + H.bars * (1 - f)} y2={barsTop + H.bars * (1 - f)} className="tl-grid" />
              <text x={4} y={barsTop + H.bars * (1 - f) - 3} className="tl-tick">
                {(yMax * f).toLocaleString()}
              </text>
            </g>
          ))}
          {bins.map((b, i) => {
            const x = px(b.a);
            const w = Math.max(1, px(b.a + bin) - x - 2);
            let yAcc = barsTop + H.bars;
            return (
              <g key={b.a} opacity={hover && hover.bin !== i ? 0.55 : 1}>
                {b.vals.map((v, s) => {
                  if (!v) return null;
                  const h = Math.max(1, (v / yMax) * H.bars);
                  yAcc -= h;
                  const gap = yAcc + h < barsTop + H.bars ? 1 : 0;
                  return (
                    <rect key={s} x={x} y={yAcc} width={w} height={Math.max(1, h - gap)}
                      rx={w > 6 && yAcc === barsTop + H.bars - (b.total / yMax) * H.bars ? 2 : 0}
                      style={{ fill: `var(--s${group ? 1 : s + 1})` }} />
                  );
                })}
              </g>
            );
          })}
          {/* 축 */}
          {ticks.map((a) => (
            <text key={a} x={Math.min(width - 18, Math.max(18, px(a)))} y={totalH - 8} className="tl-tick" textAnchor="middle">
              {fromAxis(a) < 0 ? `BC ${-fromAxis(a)}` : fromAxis(a)}
            </text>
          ))}
        </svg>

        {hover && hb && (
          <div className="tl-tip" style={{ left: Math.min(width - 230, Math.max(0, hover.x + 12)) }}>
            <strong>{binLabel(hb.a)}</strong>
            {(() => {
              const w = whoAt(hb.a);
              return (
                <small>
                  {[...w.ds, ...w.ks.slice(0, 3)].join(" · ")}
                </small>
              );
            })()}
            {hb.vals.map((v, s) =>
              v ? (
                <div key={s} className="row">
                  <i style={{ background: `var(--s${group ? 1 : s + 1})` }} />
                  {series[s].name}
                  <b>{v.toLocaleString()}</b>
                </div>
              ) : null,
            )}
            <div className="row total">
              합계 <b>{hb.total.toLocaleString()}건</b>
            </div>
            {hb.total > 0 && <small>누르면 그해 기록으로</small>}
          </div>
        )}
        {evHover && evs[evHover.i] && (
          <div className="tl-tip" style={{ left: Math.min(width - 230, Math.max(0, evHover.x + 10)), top: top.events + 22 }}>
            <strong>★ {evs[evHover.i].name}</strong>
            <small>
              {evs[evHover.i].solar} · {evs[evHover.i].src === "app" ? "주요 사건(이 앱 해설)" : "국편 주요 연표"}
            </small>
          </div>
        )}
      </div>

      {table && (
        <table className="tl-table">
          <thead>
            <tr>
              <th>연도</th>
              {series.map((s) => (
                <th key={s.key}>{s.name}</th>
              ))}
              <th>합계</th>
            </tr>
          </thead>
          <tbody>
            {bins
              .filter((b) => b.total > 0)
              .map((b) => (
                <tr key={b.a}>
                  <td>
                    <a href="#" onClick={(e) => (e.preventDefault(), goYear(fromAxis(b.a)))}>
                      {binLabel(b.a)}
                    </a>
                  </td>
                  {b.vals.map((v, s) => (
                    <td key={s}>{v ? v.toLocaleString() : ""}</td>
                  ))}
                  <td>{b.total.toLocaleString()}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
      <p className="hint">
        왕조 띠는 통설 연대, 왕 막대는 그 왕의 기록이 처음·마지막으로 나오는 해입니다(삼국·고려는 원자료 왕력, 조선은 그 왕
        실록). ★ 진한 것은 이 앱이 고른 주요 사건(해설 검수 전), 옅은 것은 국편 연표의 주요 항목입니다.{" "}
        <Link href="/kings/">조선 왕별 연표</Link>
      </p>
    </div>
  );
}
