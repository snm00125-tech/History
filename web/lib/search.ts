// 제목 검색 (pipeline/sillok/search_index.py와 같은 규칙: 공백 빼고 소문자, 두 글자 색인, crc32 % shards)
type Meta = { docs: number; chunk: number; shards: number; stop: string[] };
export type Doc = [title: string, solar: string, id: string, book: string];

const cache = new Map<string, Promise<unknown>>();
function get<T>(path: string): Promise<T> {
  if (!cache.has(path)) cache.set(path, fetch(`/data/s/${path}`).then((r) => (r.ok ? r.json() : {})));
  return cache.get(path) as Promise<T>;
}

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

export const norm = (s: string) => s.replace(/\s+/g, "").toLowerCase();
function bigrams(s: string) {
  const t = [...norm(s)];
  const out = new Set<string>();
  for (let i = 0; i < t.length - 1; i++) out.add(t[i] + t[i + 1]);
  return [...out];
}

export type Candidates = { ids: number[]; usable: number; skipped: number } | { error: string };

/** 후보 문서 번호(날짜순). 흔한 두 글자는 건너뛰고, 쓸 수 있는 두 글자가 없으면 오류. */
export async function candidates(q: string): Promise<Candidates> {
  const meta = await get<Meta>("meta.json");
  const nq = norm(q);
  if ([...nq].length < 2) return { error: "두 글자 이상 입력해 주세요." };
  const stop = new Set(meta.stop);
  const all = bigrams(nq);
  const bgs = all.filter((b) => !stop.has(b));
  if (!bgs.length) return { error: "너무 흔한 말이라 찾을 수 없습니다. 더 구체적인 말을 넣어 주세요." };
  const lists = await Promise.all(
    bgs.map(async (b) => {
      const shard = await get<Record<string, number[]>>(`i/${crc32(b) % meta.shards}.json`);
      const enc = shard[b] ?? [];
      const out: number[] = [];
      let p = 0;
      for (const d of enc) out.push((p += d));
      return out;
    }),
  );
  lists.sort((a, b) => a.length - b.length);
  let cur = lists[0];
  for (const l of lists.slice(1)) {
    const s = new Set(l);
    cur = cur.filter((x) => s.has(x));
    if (!cur.length) break;
  }
  return { ids: cur, usable: bgs.length, skipped: all.length - bgs.length };
}

/** 후보를 순서대로 확인해 제목에 질의가 그대로 든 것만 최대 n개. 다음 시작 위치도 돌려준다. */
export async function verify(q: string, ids: number[], from: number, n: number) {
  const meta = await get<Meta>("meta.json");
  const nq = norm(q);
  const out: Doc[] = [];
  let i = from;
  while (i < ids.length && out.length < n) {
    const k = Math.floor(ids[i] / meta.chunk);
    const chunk = await get<Doc[]>(`d/${k}.json`);
    while (i < ids.length && Math.floor(ids[i] / meta.chunk) === k && out.length < n) {
      const d = chunk[ids[i] - k * meta.chunk];
      if (d && norm(d[0]).includes(nq)) out.push(d);
      i++;
    }
  }
  return { docs: out, next: i };
}

/** 문서 번호들 → 문서(제목·날짜·ID·책). 덩어리 단위로 받아 온다. */
export async function docsByIds(ids: number[]): Promise<Doc[]> {
  const meta = await get<Meta>("meta.json");
  const out: Doc[] = [];
  for (const i of ids) {
    const k = Math.floor(i / meta.chunk);
    const chunk = await get<Doc[]>(`d/${k}.json`);
    const d = chunk[i - k * meta.chunk];
    if (d) out.push(d);
  }
  return out;
}
