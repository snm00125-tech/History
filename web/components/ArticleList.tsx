"use client";

import { useState } from "react";
import type { Article } from "@/lib/types";
import { GROUP_NAMES } from "@/lib/format";
import ArticleCard from "./ArticleCard";

/** 분류 묶음으로 거르는 기사 목록 */
export default function ArticleList({ articles }: { articles: Article[] }) {
  const [grp, setGrp] = useState<string | null>(null);
  const counts = new Map<string, number>();
  for (const a of articles) for (const g of a.groups) counts.set(g, (counts.get(g) ?? 0) + 1);
  const shown = grp ? articles.filter((a) => a.groups.includes(grp)) : articles;
  return (
    <>
      {counts.size > 1 && (
        <div className="filters" role="group" aria-label="분류">
          <button type="button" className={grp === null ? "chip on" : "chip"} onClick={() => setGrp(null)}>
            전체 {articles.length}
          </button>
          {Object.keys(GROUP_NAMES).filter((g) => counts.has(g)).map((g) => (
            <button key={g} type="button" className={grp === g ? "chip on" : "chip"} onClick={() => setGrp(grp === g ? null : g)}>
              {GROUP_NAMES[g]} {counts.get(g)}
            </button>
          ))}
        </div>
      )}
      {shown.map((a) => <ArticleCard key={a.id} a={a} />)}
    </>
  );
}
