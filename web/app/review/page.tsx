"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { type Index, loadIndex } from "@/lib/data";

type Item = { id: string; t: string; lunarDay: number | null; ganji: string | null; solar: string | null; tableSolar: string | null };
type Group = { key: string; book: string; bookName: string; lunarMonth: string; status: string; label: string; delta: number | null; items: Item[] };

const STORE = "history-review-done";
function readDone(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(STORE) ?? "{}");
  } catch {
    return {};
  }
}

export default function ReviewPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [idx, setIdx] = useState<Index | null>(null);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [hideDone, setHideDone] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/review.json").then((r) => r.json()).then(setGroups);
    loadIndex().then(setIdx);
    setDone(readDone());
  }, []);

  function toggle(key: string) {
    const next = { ...done, [key]: !done[key] };
    setDone(next);
    try {
      localStorage.setItem(STORE, JSON.stringify(next));
    } catch {}
  }

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    groups.forEach((g) => (c[g.status] = (c[g.status] ?? 0) + g.items.length));
    return c;
  }, [groups]);
  const labels = Object.fromEntries(groups.map((g) => [g.status, g.label]));
  const shown = groups.filter((g) => (!status || g.status === status) && (!hideDone || !done[g.key]));
  const total = groups.reduce((a, g) => a + g.items.length, 0);
  const doneItems = groups.filter((g) => done[g.key]).reduce((a, g) => a + g.items.length, 0);
  void idx;

  return (
    <div className="reviewview">
      <h2>날짜 검수</h2>
      <p className="hint">
        기사 머리의 일진(날짜 간지)과 음력 표가 맞지 않은 기사입니다. 한 달이 통째로 같은 날수만큼 밀린 경우가 많아, 같은 책·같은
        달·같은 차이끼리 묶었습니다. 확인한 묶음에 표시하면 이 브라우저에 기억됩니다.
      </p>
      <p className="stats">
        전체 {total.toLocaleString()}건 · {groups.length}묶음 · 확인함 {doneItems.toLocaleString()}건
      </p>
      <div className="filters">
        <button className={!status ? "on" : ""} onClick={() => setStatus(null)}>
          전체
        </button>
        {Object.entries(counts).map(([s, n]) => (
          <button key={s} className={status === s ? "on" : ""} onClick={() => setStatus(s)}>
            {labels[s]} {n.toLocaleString()}
          </button>
        ))}
        <label className="chk">
          <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} /> 확인한 묶음 숨기기
        </label>
      </div>
      <ul className="rgroups">
        {shown.map((g) => (
          <li key={g.key} className={done[g.key] ? "done" : ""}>
            <div className="rg-head">
              <input type="checkbox" checked={!!done[g.key]} onChange={() => toggle(g.key)} aria-label="확인함" />
              <button className="rg-title" onClick={() => setOpen(open === g.key ? null : g.key)}>
                <strong>
                  {g.bookName} {g.lunarMonth}
                </strong>{" "}
                · {g.label}
                {g.delta ? ` (${g.delta > 0 ? "+" : ""}${g.delta}일)` : ""} · {g.items.length}건 {open === g.key ? "▲" : "▼"}
              </button>
            </div>
            {open === g.key && (
              <table className="rtable">
                <thead>
                  <tr>
                    <th>음력 일</th>
                    <th>원문 일진</th>
                    <th>표 날짜</th>
                    <th>쓰는 날짜</th>
                    <th>기사</th>
                  </tr>
                </thead>
                <tbody>
                  {g.items.map((it) => {
                    const d = it.solar ?? it.tableSolar;
                    return (
                      <tr key={it.id}>
                        <td>{it.lunarDay ?? "?"}일</td>
                        <td>{it.ganji ?? "-"}</td>
                        <td>{it.tableSolar ?? "-"}</td>
                        <td>{it.solar ?? "-"}</td>
                        <td>
                          {d ? (
                            <Link href={`/view/?ym=${d.slice(0, 7)}&d=${Number(d.slice(8))}#${it.id}`}>{it.t || it.id}</Link>
                          ) : (
                            it.t || it.id
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
