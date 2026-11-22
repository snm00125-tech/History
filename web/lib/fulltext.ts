// 원문(한문) 본문 검색 (pipeline/sillok/fulltext_index.py와 같은 규칙: 글자·숫자만 남기고 소문자, 두 글자 색인)
import { type Article, loadMonth } from "@/lib/data";
import { type Doc, docsByIds } from "@/lib/search";

type Meta = { docs: number; shards: number; cut: number };
const cache = new Map<string, Promise<unknown>>();
function get<T>(path: string, empty: T): Promise<T> {
  if (!cache.has(path)) cache.set(path, fetch(`/data/${path}`).then((r) => (r.ok ? r.json() : empty)));
  return cache.get(path) as Promise<T>;
}

const KEEP = /[\p{L}\p{N}]/u;
export const fnorm = (s: string) => s.replace(/[^\p{L}\p{N}]+/gu, "").toLowerCase();

const TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(s: string) {
  let c = 0xffffffff;
  for (const b of new TextEncoder().encode(s)) c = TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function decode(b64: string): number[] {
  const bin = atob(b64);
  const out: number[] = [];
  let x = 0,
    shift = 0,
    prev = 0;
  for (let i = 0; i < bin.length; i++) {
    const byte = bin.charCodeAt(i);
    x |= (byte & 0x7f) << shift;
    if (byte & 0x80) shift += 7;
    else {
      prev += x;
      out.push(prev);
      x = 0;
      shift = 0;
    }
  }
  return out;
}

/** 후보 문서 번호. 색인에 없는 두 글자(아주 흔하거나 아예 없는 말)는 건너뛰고, 확인 단계에서 거른다. */
export async function ftCandidates(q: string): Promise<{ ids: number[] } | { error: string }> {
  const nq = fnorm(q);
  const chars = [...nq];
  if (chars.length < 2) return { error: "두 글자 이상 입력해 주세요." };
  const meta = await get<Meta>("f/meta.json", { docs: 0, shards: 4096, cut: 0 });
  const bgs = [...new Set(chars.slice(0, -1).map((c, i) => c + chars[i + 1]))];
  const lists: number[][] = [];
  await Promise.all(
    bgs.map(async (b) => {
      const shard = await get<Record<string, string>>(`f/${crc32(b) % meta.shards}.json`, {});
      if (shard[b]) lists.push(decode(shard[b]));
    }),
  );
  if (!lists.length)
    return { error: "너무 흔한 글자 조합이라 찾을 수 없습니다(예: 上曰). 글자를 더 넣어 주세요." };
  lists.sort((a, b) => a.length - b.length);
  let cur = lists[0];
  for (const l of lists.slice(1)) {
    const s = new Set(l);
    cur = cur.filter((x) => s.has(x));
    if (!cur.length) break;
  }
  return { ids: cur };
}

export type FtHit = { doc: Doc; before: string; match: string; after: string };

async function articleText(doc: Doc): Promise<string | null> {
  const [, solar, id] = doc;
  if (!solar) {
    const und = await get<Article[]>("undated.json", []);
    return und.find((a) => a.id === id)?.x ?? null;
  }
  const mf = await loadMonth(solar.slice(0, 7)).catch(() => null);
  if (!mf) return null;
  for (const d of mf.days) for (const a of d.articles) if (a.id === id) return a.x;
  return mf.monthly.find((a) => a.id === id)?.x ?? null;
}

function snippet(text: string, nq: string): Omit<FtHit, "doc"> | null {
  const pos: number[] = [];
  let norm = "";
  for (let i = 0; i < text.length; ) {
    const ch = String.fromCodePoint(text.codePointAt(i)!);
    if (KEEP.test(ch)) {
      const low = ch.toLowerCase();
      for (let k = 0; k < low.length; k++) pos.push(i);
      norm += low;
    }
    i += ch.length;
  }
  const at = norm.indexOf(nq);
  if (at < 0) return null;
  const s = pos[at];
  const e = pos[at + nq.length - 1] + 1;
  return { before: text.slice(Math.max(0, s - 40), s), match: text.slice(s, e), after: text.slice(e, e + 40) };
}

/** 후보를 from부터 확인해 원문에 질의가 든 것만 최대 n개. scanLimit개까지만 보고 멈춘다. */
export async function ftVerify(q: string, ids: number[], from: number, n: number, scanLimit = 600) {
  const nq = fnorm(q);
  const hits: FtHit[] = [];
  let i = from;
  while (i < ids.length && hits.length < n && i - from < scanLimit) {
    const batch = ids.slice(i, i + 40);
    const docs = await docsByIds(batch);
    for (const doc of docs) {
      i++;
      const t = await articleText(doc);
      const sn = t ? snippet(t, nq) : null;
      if (sn) hits.push({ doc, ...sn });
      if (hits.length >= n) break;
    }
    if (!docs.length) i += batch.length;
  }
  return { hits, next: i };
}
