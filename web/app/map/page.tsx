"use client";

// 지도: 고른 기간의 기록에 나온 지명을 원 크기(기사 수)로. 원을 누르면 그 지명이 나온 기사 목록.
import "leaflet/dist/leaflet.css";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { type Index, loadIndex, yearLabel } from "@/lib/data";
import { type Doc, docsByIds } from "@/lib/search";

type Place = {
  i: number;
  h: string;
  ko: string | null;
  lat: number;
  lon: number;
  kind: "place" | "province";
  qid: string | null;
  cands: number;
  n: number;
  dec: Record<string, number>;
};
type State = { h: string; ko: string | null; n: number };

const PRESETS: [string, number, number][] = [
  ["전체", -800, 2010],
  ["고려", 918, 1391],
  ["조선 전기", 1392, 1591],
  ["임진왜란", 1592, 1598],
  ["조선 후기", 1599, 1863],
  ["개항~대한제국", 1864, 1910],
];
const CHUNK = 40;

function countIn(p: Place, from: number, to: number) {
  let n = 0;
  for (const [d, c] of Object.entries(p.dec)) {
    const dec = Number(d);
    if (dec + 9 >= from && dec <= to) n += c;
  }
  return n;
}

export default function MapPage() {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [states, setStates] = useState<State[]>([]);
  const [idx, setIdx] = useState<Index | null>(null);
  const [range, setRange] = useState<[number, number]>([1392, 1910]);
  const [sel, setSel] = useState<Place | null>(null);
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [limit, setLimit] = useState(50);
  const [err, setErr] = useState("");
  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const LRef = useRef<typeof import("leaflet") | null>(null);

  useEffect(() => {
    Promise.all([fetch("/data/geo/places.json"), fetch("/data/geo/states.json")])
      .then(async ([a, b]) => {
        if (!a.ok) throw new Error(String(a.status));
        setPlaces(await a.json());
        setStates(b.ok ? await b.json() : []);
      })
      .catch((e) => setErr(`지도 자료를 못 읽었습니다 (${e})`));
    loadIndex().then(setIdx).catch(() => {});
  }, []);

  // 지도 만들기 (브라우저에서만)
  useEffect(() => {
    let alive = true;
    import("leaflet").then((L) => {
      if (!alive || !mapEl.current || mapRef.current) return;
      LRef.current = L;
      const m = L.map(mapEl.current, { center: [37.5, 127.5], zoom: 6, minZoom: 4, maxZoom: 13 });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · 좌표: 위키데이터',
        maxZoom: 19,
      }).addTo(m);
      layerRef.current = L.layerGroup().addTo(m);
      mapRef.current = m;
      setTick((t) => t + 1);
    });
    return () => {
      alive = false;
    };
  }, []);
  const [tick, setTick] = useState(0);

  const [from, to] = range;
  const counted = useMemo(
    () =>
      (places ?? [])
        .map((p) => ({ p, c: countIn(p, from, to) }))
        .filter((x) => x.c > 0)
        .sort((a, b) => b.c - a.c),
    [places, from, to],
  );
  const maxC = counted[0]?.c ?? 1;

  // 원 그리기
  useEffect(() => {
    const L = LRef.current;
    const layer = layerRef.current;
    if (!L || !layer) return;
    layer.clearLayers();
    for (const { p, c } of [...counted].reverse()) {
      const r = 3 + 22 * Math.sqrt(c / maxC);
      if (p.kind === "province") {
        L.marker([p.lat, p.lon], {
          icon: L.divIcon({ className: "map-prov", html: `${p.ko ?? p.h}<small>${c.toLocaleString()}</small>` }),
        })
          .on("click", () => pick(p))
          .addTo(layer);
        continue;
      }
      L.circleMarker([p.lat, p.lon], {
        radius: r,
        weight: 1.5,
        className: sel?.i === p.i ? "map-dot sel" : "map-dot",
      })
        .bindTooltip(`${p.ko ?? ""} ${p.h} · ${c.toLocaleString()}건${p.cands > 1 ? " (같은 이름 여러 곳)" : ""}`)
        .on("click", () => pick(p))
        .addTo(layer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [counted, maxC, tick, sel?.i]);

  async function pick(p: Place) {
    setSel(p);
    setDocs(null);
    setLimit(50);
    const chunk = await fetch(`/data/geo/d/${Math.floor(p.i / CHUNK)}.json`).then((r) => r.json());
    const list: [number, number][] = chunk[p.i] ?? [];
    const ids = list.filter(([y]) => y >= from && y <= to).map(([, d]) => d);
    setDocIds(ids);
  }
  const [docIds, setDocIds] = useState<number[]>([]);
  useEffect(() => {
    if (!sel) return;
    docsByIds(docIds.slice(0, limit)).then(setDocs);
  }, [docIds, limit, sel]);
  // 기간을 바꾸면 고른 지명 목록도 다시
  useEffect(() => {
    if (sel) pick(sel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [from, to]);

  const books = idx?.books ?? {};
  return (
    <div className="mapview">
      <h1>지도로 보기</h1>
      <p className="hint">
        고른 기간의 기록(실록·고려사 등 원문 지명 색인)에 나온 지명을 원 크기로 보여 줍니다. 원을 누르면 그 지명이 나온 기사
        목록이 나옵니다.
      </p>
      <div className="filters">
        {PRESETS.map(([n, a, b]) => (
          <button key={n} className={from === a && to === b ? "on" : ""} onClick={() => setRange([a, b])}>
            {n}
          </button>
        ))}
        <label className="yr">
          <input type="number" value={from} onChange={(e) => setRange([Number(e.target.value), to])} aria-label="시작 연도" />
          ~
          <input type="number" value={to} onChange={(e) => setRange([from, Number(e.target.value)])} aria-label="끝 연도" />년
        </label>
      </div>
      {err && <p className="error">{err}</p>}
      <div className="map-grid">
        <div ref={mapEl} className="map-box" />
        <aside className="map-side">
          {sel ? (
            <>
              <button className="linkish" onClick={() => setSel(null)}>
                ← 많이 나온 곳
              </button>
              <h2>
                {sel.ko ?? sel.h} <small>{sel.h}</small>
              </h2>
              <p className="hint">
                {yearLabel(from)}~{yearLabel(to)} 기사 {docIds.length.toLocaleString()}건 · 전체 {sel.n.toLocaleString()}건
                {sel.kind === "province" && " · 도(道) 이름이라 점은 지금 남·북도의 가운데"}
                {sel.cands > 1 && ` · 같은 이름 후보 ${sel.cands}곳 중 하나(위치 검수 전)`}
                {sel.qid && !sel.qid.includes("+") && (
                  <>
                    {" · "}
                    <a href={`https://www.wikidata.org/wiki/${sel.qid}`} target="_blank" rel="noreferrer">
                      위키데이터
                    </a>
                  </>
                )}
              </p>
              {!docs && <p className="hint">불러오는 중…</p>}
              <ul className="results">
                {(docs ?? []).map(([t, solar, id, b]) => (
                  <li key={id}>
                    <Link href={`/view/?ym=${solar.slice(0, -3)}&d=${Number(solar.slice(-2))}#${id}`}>
                      <span className="r-date">{solar.replaceAll("-", ".")}</span>
                      <span className="r-title">{t}</span>
                    </Link>
                    <span className="r-book">{books[b] ?? b}</span>
                  </li>
                ))}
              </ul>
              {docs && limit < docIds.length && (
                <button className="morebtn" onClick={() => setLimit((l) => l + 100)}>
                  더 보기
                </button>
              )}
            </>
          ) : (
            <>
              <h2>
                많이 나온 곳 <small>{yearLabel(from)}~{yearLabel(to)}</small>
              </h2>
              <ol className="map-top">
                {counted.slice(0, 25).map(({ p, c }) => (
                  <li key={p.i}>
                    <button className="linkish" onClick={() => pick(p)}>
                      {p.ko ?? p.h} <small>{p.h}</small>
                    </button>
                    <span>{c.toLocaleString()}</span>
                  </li>
                ))}
              </ol>
              <h3>나라·종족 이름 (점으로 안 그림, 전체 기간)</h3>
              <p className="map-states">
                {states.slice(0, 20).map((s) => (
                  <span key={s.h}>
                    {s.h}
                    {s.ko ? `(${s.ko})` : ""} {s.n.toLocaleString()}
                  </span>
                ))}
              </p>
            </>
          )}
        </aside>
      </div>
      <p className="hint">
        좌표는 위키데이터에서 한자·한글 지명으로 찾은 것(검수 전)입니다. 같은 이름이 여러 곳이면 행정구역을 먼저 골랐습니다. 지명
        색인은 국사편찬위원회 원문 색인(실록·고려사 등)이고, 상위 3,000개 지명 중 위치를 찾은 {places?.length.toLocaleString()}
        곳만 그립니다.
      </p>
    </div>
  );
}
