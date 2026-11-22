"""공공데이터포털 원자료 내려받기·풀기 (data/raw/ 아래). 이미 있으면 건너뛴다.

    python3 tools/fetch_raw.py            # 전부
    python3 tools/fetch_raw.py 15053647   # 하나만

파일 ID(atchFileId)는 데이터 갱신 때 바뀌므로 상세 페이지에서 매번 새로 얻는다.
내려받은 파일은 신뢰할 수 없는 자료로 다룬다(풀기만 하고 그 안에서 아무것도 실행하지 않는다).
"""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

RAW = Path(__file__).parents[1] / "data" / "raw"
DATASETS = {
    "15053647": "sillok_15053647",   # 조선왕조실록 원문(태조~철종)
    "15053646": "sillok_15053646",   # 고종·순종실록 원문
    "15053636": "khdb_15053636",     # 비변사등록 원문
    "15053632": "khdb_15053632",     # 한국사료총서 원문
    "15053645": "person_15053645",   # 실록 부가정보 인물
}
UA = {"User-Agent": "Mozilla/5.0 (history-timeline data fetch)"}


def _get(url: str) -> bytes:
    """data.go.kr은 연결이 가끔 끊긴다 → curl로 여러 번 다시 시도."""
    r = subprocess.run(["curl", "-sS", "--retry", "6", "--retry-all-errors", "--retry-delay", "3", "--max-time", "120",
                        "-A", UA["User-Agent"], url], capture_output=True, check=True)
    return r.stdout


def file_id(pk: str) -> str:
    page = _get(f"https://www.data.go.kr/data/{pk}/fileData.do").decode("utf-8", "replace")
    m = re.search(rf"fn_fileDataDown\('{pk}', '([^']+)'", page)
    if not m:
        raise SystemExit(f"{pk}: 상세 페이지에서 내려받기 정보를 찾지 못함")
    info = _get(f"https://www.data.go.kr/tcs/dss/selectFileDataDownload.do?publicDataPk={pk}"
                f"&publicDataDetailPk={m[1]}&fileDetailSn=1").decode("utf-8", "replace")
    fid = re.search(r'"atchFileId"\s*:\s*"(FILE_\d+)"', info)
    if not fid:
        raise SystemExit(f"{pk}: atchFileId 없음")
    return fid[1]


def fetch(pk: str) -> None:
    d = RAW / DATASETS[pk]
    x = d / "x"
    if x.exists() and any(p.suffix in (".xml", ".csv") for p in x.rglob("*")):
        print(f"{pk}: 있음, 건너뜀")
        return
    d.mkdir(parents=True, exist_ok=True)
    fid = file_id(pk)
    z = d / "src.zip"
    print(f"{pk}: 내려받는 중 ({fid})")
    subprocess.run(["curl", "-sSL", "--retry", "6", "--retry-all-errors", "-o", str(z),
                    f"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={fid}&fileDetailSn=1"], check=True)
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():  # 경로 탈출 막기
            if n.startswith("/") or ".." in Path(n).parts:
                raise SystemExit(f"{pk}: 수상한 경로 {n}")
        zf.extractall(x)
    print(f"{pk}: 풀었음 → {x}")


if __name__ == "__main__":
    for pk in (sys.argv[1:] or DATASETS):
        fetch(pk)
