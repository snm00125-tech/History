"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { solarToJdn } from "@/lib/format";

/** 양력 날짜를 넣으면 그날(없으면 가장 가까운 기록 날)로 간다. */
export default function DateJump({ days, min, max }: { days: number[]; min: string; max: string }) {
  const router = useRouter();
  const [v, setV] = useState("1592-05-23");
  const [msg, setMsg] = useState("");

  function go(e: React.FormEvent) {
    e.preventDefault();
    const [y, m, d] = v.split("-").map(Number);
    const j = y && m && d ? solarToJdn(y, m, d) : null;
    if (j === null) { setMsg("날짜를 확인해 주세요."); return; }
    let best = days[0];
    for (const x of days) if (Math.abs(x - j) < Math.abs(best - j)) best = x;
    setMsg(best === j ? "" : "그날 기록이 없어 가장 가까운 날로 갑니다.");
    router.push(`/d/${best}/`);
  }

  return (
    <form className="jump" onSubmit={go}>
      <label htmlFor="jump-date">양력 날짜로 찾기</label>
      <input id="jump-date" type="date" min={min} max={max} value={v} onChange={(e) => setV(e.target.value)} />
      <button type="submit">이동</button>
      {msg && <span className="meta">{msg}</span>}
    </form>
  );
}
