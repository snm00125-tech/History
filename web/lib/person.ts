// 인물 (pipeline/sillok/export_person.py 출력)
const CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";
const SHARD = 500;

export type PersonHit = [id: string, ko: string, hj: string, born: number | null, died: number | null, kind: string, n: number, first: number, last: number];
export type Person = {
  ko?: string;
  hj?: string;
  ja?: string;
  ho?: string;
  siho?: string;
  bon?: string;
  born?: number;
  died?: number;
  kind?: string;
  docs: number[]; // 차분 부호화
  off: [solar: string, office: string, status: string, doc: number][];
  yc?: Record<string, number>; // 연도별 기사 수
  co?: [id: string, ko: string, n: number][]; // 같은 기사에 자주 함께 나오는 인물
  wiki?: {
    qid: string;
    title: string | null;
    match: string;
    summary?: string;
    url?: string;
    img?: { thumb: string; page: string; license: string; artist: string; desc: string };
  };
};

const cache = new Map<string, Promise<unknown>>();
function get<T>(path: string, empty: T): Promise<T> {
  if (!cache.has(path)) cache.set(path, fetch(`/data/${path}`).then((r) => (r.ok ? r.json() : empty)));
  return cache.get(path) as Promise<T>;
}

export function choseong(s: string) {
  const c = s.charCodeAt(0) - 0xac00;
  return c >= 0 && c < 11172 ? CHO[Math.floor(c / 588)] : "etc";
}

/** 이름으로 찾기: 정확히 같은 이름 먼저, 그다음 그 글자로 시작하는 이름. 언급 많은 순. */
export async function findPersons(q: string, limit = 30): Promise<PersonHit[]> {
  const t = q.replace(/\s+/g, "");
  if (!t) return [];
  const list = await get<PersonHit[]>(`pi/${choseong(t)}.json`, []);
  const exact = list.filter((p) => p[1] === t || p[2] === t);
  const prefix = t.length >= 2 ? list.filter((p) => p[1] !== t && p[1]?.startsWith(t)) : [];
  return [...exact, ...prefix].slice(0, limit);
}

export async function loadPerson(id: string): Promise<Person | null> {
  const n = Math.floor(Number(id.slice(2)) / SHARD);
  const shard = await get<Record<string, Person>>(`p/${n}.json`, {});
  return shard[id] ?? null;
}

export function decodeDocs(enc: number[]) {
  const out: number[] = [];
  let p = 0;
  for (const d of enc) out.push((p += d));
  return out;
}
