#!/usr/bin/env bash
# 원자료 내려받기 → 작업 DB 적재 → 요약 다시 넣기 → 웹 데이터 내보내기 → 사이트 빌드. 새 세션에서 한 번에.
#   bash pipeline/tools/rebuild_all.sh          # 전부 (약 20분)
#   SKIP_BUILD=1 bash pipeline/tools/rebuild_all.sh   # 사이트 빌드 빼고
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/fetch_raw.py
rm -f data/work.sqlite
python3 -m sillok.load data/raw/sillok_15053647/x data/work.sqlite
python3 -m sillok.load data/raw/sillok_15053646/x data/work.sqlite
for f in summaries/*.jsonl; do
  case "$f" in *pilot*) a=pilot-session;; *) a=session-agent;; esac
  python3 -c "import sys; from sillok.summary import load_jsonl; n,e=load_jsonl('data/work.sqlite',sys.argv[1],sys.argv[2]); print(sys.argv[1],n,'오류',len(e))" "$f" "$a"
done
python3 -m sillok.load_bb data/raw/khdb_15053636/x data/work.sqlite
python3 -m sillok.load_sa data/raw/khdb_15053632/x data/work.sqlite
python3 -m sillok.load_kh data/raw data/work.sqlite
python3 -m sillok.load_sjw data/raw/sjw_15064218/x data/work.sqlite
python3 -m sillok.load_itkc data/raw/itkc_15141442/x data/work.sqlite
python3 -m sillok.load_jh data/raw data/work.sqlite
python3 -m sillok.load_person data/raw/person_15053645/x data/work.sqlite
python3 -m sillok.date_review data/work.sqlite
python3 -m pytest -q
python3 -m sillok.export data/work.sqlite ../web/public/data
if [ -z "${SKIP_BUILD:-}" ]; then
  cd ../web
  [ -d node_modules ] || npm install --no-audit --no-fund
  npx next build
fi
echo "완료"
