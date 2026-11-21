"""요약 일괄 생성 (Claude Message Batches API).

흐름: prepare → submit → status → collect → (retry → submit → collect)…
작업 폴더 data/gen/<이름>/ (git 제외). 검증을 통과한 결과만 summaries/<이름>.jsonl에 쌓는다.

    python -m sillok.generate prepare data/work.sqlite <이름> --years 1592 1592 --months 5 [--limit N]
    python -m sillok.generate submit  data/work.sqlite <이름>          # 돈이 드는 단계
    python -m sillok.generate status  data/work.sqlite <이름>
    python -m sillok.generate collect data/work.sqlite <이름>
    python -m sillok.generate retry   data/work.sqlite <이름>          # 실패분을 오류와 함께 다시 준비

- 모델 claude-opus-5-5, adaptive thinking, effort high(정확성 우선), JSON 스키마 출력.
- 시스템 지침(sillok/prompt.py)은 모든 요청에서 같아 1시간 캐시로 공유한다.
- 이미 요약이 있는 기사(파일럿 등)는 건너뛴다.
- API 키: HISTORY_ANTHROPIC_API_KEY (ANTHROPIC_API_KEY를 쓰면 Claude Code 과금과 섞일 수 있어 피한다). 접속 주소는 HISTORY_ANTHROPIC_BASE_URL(기본 api.anthropic.com).
  (이 환경의 ANTHROPIC_BASE_URL은 Claude Code용이라 쓰지 않는다.)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from .prompt import PROMPT_VERSION, SCHEMA, system_prompt, user_message
from .summary import SummaryError, check, load_jsonl

MODEL = "claude-opus-5-5"
EFFORT = "high"
MAX_TOKENS = 16000
ROOT = Path(__file__).parents[1]
# 달러/100만 토큰, Message Batches(표준가의 50%). 2026-11 기준 표준가(입력/출력/캐시 읽기):
#   Opus 5.5 $4/$20/$0.20, Sonnet 5.5 $2/$10/$0.10, Haiku 5.5 $0.10/$0.50(캐시 읽기는 입력의 0.1배로 가정).
# 1시간 캐시 쓰기는 입력가의 2배. 실제 청구액은 콘솔에서 확인한다.
PRICES = {
    "claude-opus-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.10, "cache_write_1h": 4.00},
    "claude-sonnet-5-5": {"input": 1.00, "output": 5.00, "cache_read": 0.05, "cache_write_1h": 2.00},
    "claude-haiku-5-5": {"input": 0.05, "output": 0.25, "cache_read": 0.005, "cache_write_1h": 0.10},
}
MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
MAX_ROUNDS = 3  # 첫 요청 + 재요청 2번


def _no_key():
    raise SystemExit("HISTORY_ANTHROPIC_API_KEY 환경 변수가 없음 (History 환경 설정 → 환경 변수에 추가 후 새 세션)")


def _client():
    import anthropic  # 생성 단계에서만 필요
    return anthropic.Anthropic(
        base_url=os.environ.get("HISTORY_ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        # Claude Code 자체 과금과 섞이지 않도록 전용 변수 이름을 쓴다
        api_key=os.environ.get("HISTORY_ANTHROPIC_API_KEY") or _no_key(),
        max_retries=4,
    )


def cid(aid: str) -> str:
    """custom_id는 [A-Za-z0-9_-]{1,64}만 허용. 일 미상 기사 ID의 '?'를 바꾼다."""
    return aid.replace("?", "Q")


def _dir(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        raise SystemExit(f"이름은 영문·숫자·_-만: {name}")
    d = ROOT / "data" / "gen" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state(d: Path) -> dict:
    p = d / "state.json"
    return json.loads(p.read_text()) if p.exists() else {"rounds": []}


def _save_state(d: Path, st: dict) -> None:
    (d / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1))


def _params(system: str, messages: list[dict], model: str = MODEL) -> dict:
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        "messages": messages,
    }


def select(con, years, months, books, limit) -> list[str]:
    q = ["SELECT id FROM article WHERE id NOT IN (SELECT article_id FROM summary)",
         "AND lunar_year BETWEEN ? AND ?"]
    args: list = list(years)
    if months:
        q.append(f"AND lunar_month IN ({','.join('?' * len(months))})")
        args += months
    q.append(f"AND book IN ({','.join('?' * len(books))}) ORDER BY lunar_year, lunar_month, lunar_leap, id")
    ids = [r[0] for r in con.execute(" ".join(q), [*args, *books])]
    return ids[:limit] if limit else ids


def estimate(con, ids, system, model: str = MODEL) -> dict:
    PRICE = PRICES[model]
    """대략 비용 추정(실측 전). 한문 1자≈1.3토큰, 한글 1자≈1토큰으로 잡는다. 출력은 thinking 포함 기사당 평균을 가정."""
    chars = sum(len(con.execute("SELECT text FROM article WHERE id=?", (i,)).fetchone()[0]) for i in ids)
    inp = chars * 1.3 + len(ids) * 150
    sys_tok = len(system) * 1.2
    out_lo, out_hi = len(ids) * 800, len(ids) * 2500
    cost = lambda o: (inp * PRICE["input"] + sys_tok * PRICE["cache_write_1h"]
                      + sys_tok * len(ids) * PRICE["cache_read"] + o * PRICE["output"]) / 1e6
    return {"articles": len(ids), "source_chars": chars, "usd_low": round(cost(out_lo), 2),
            "usd_high": round(cost(out_hi), 2),
            "note": "추정치. 작은 묶음을 먼저 돌려 collect의 실측 비용으로 다시 계산할 것."}


def cmd_prepare(con, name, args):
    d = _dir(name)
    st = _state(d)
    if st["rounds"]:
        raise SystemExit(f"{d}에 이미 진행 중인 작업이 있음")
    model = MODELS[args.model]
    ids = args.ids or select(con, args.years, args.months, args.books, args.limit)
    if not ids:
        raise SystemExit("대상 기사 없음")
    system = system_prompt(con)
    with open(d / "round1.requests.jsonl", "w", encoding="utf-8") as f:
        for aid in ids:
            msgs = [{"role": "user", "content": user_message(con, aid)}]
            f.write(json.dumps({"custom_id": cid(aid), "article_id": aid,
                                "params": _params(system, msgs, model)}, ensure_ascii=False) + "\n")
    est = estimate(con, ids, system, model)
    st["model"] = model
    st["rounds"].append({"n": 1, "requests": "round1.requests.jsonl", "count": len(ids),
                         "batch_id": None, "prompt_version": PROMPT_VERSION, "estimate": est})
    _save_state(d, st)
    print(json.dumps(est, ensure_ascii=False, indent=1))


def cmd_submit(con, name, args):
    from anthropic.types.messages.batch_create_params import Request
    d = _dir(name)
    st = _state(d)
    r = st["rounds"][-1]
    if r.get("batch_id"):
        raise SystemExit(f"이미 제출됨: {r['batch_id']}")
    reqs = [json.loads(x) for x in open(d / r["requests"], encoding="utf-8")]
    batch = _client().messages.batches.create(
        requests=[Request(custom_id=q["custom_id"], params=q["params"]) for q in reqs])
    r["batch_id"] = batch.id
    r["submitted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _save_state(d, st)
    print(f"제출: {batch.id} ({len(reqs)}건)")


def cmd_status(con, name, args):
    st = _state(_dir(name))
    b = _client().messages.batches.retrieve(st["rounds"][-1]["batch_id"])
    print(b.processing_status, b.request_counts)


def _cost(u: dict, model: str) -> float:
    PRICE = PRICES[model]
    return round((u["input_tokens"] * PRICE["input"] + u["output_tokens"] * PRICE["output"]
                  + u["cache_read_input_tokens"] * PRICE["cache_read"]
                  + u["cache_creation_input_tokens"] * PRICE["cache_write_1h"]) / 1e6, 4)


def cmd_collect(con, name, args):
    d = _dir(name)
    st = _state(d)
    r = st["rounds"][-1]
    client = _client()
    b = client.messages.batches.retrieve(r["batch_id"])
    if b.processing_status != "ended":
        raise SystemExit(f"아직 처리 중: {b.processing_status} {b.request_counts}")
    reqs = {q["custom_id"]: q for q in map(json.loads, open(d / r["requests"], encoding="utf-8"))}
    no_load = getattr(args, "no_load", False)
    out_path = (d / "out.jsonl") if no_load else (ROOT / "summaries" / f"{name}.jsonl")
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    ok, failures = 0, []
    with open(out_path, "a", encoding="utf-8") as out:
        for res in client.messages.batches.results(r["batch_id"]):
            q = reqs[res.custom_id]
            aid = q["article_id"]
            if res.result.type != "succeeded":
                failures.append({"article_id": aid, "error": f"batch:{res.result.type}", "answer": None})
                continue
            msg = res.result.message
            for k in usage:
                usage[k] += getattr(msg.usage, k, 0) or 0
            if msg.stop_reason != "end_turn":
                failures.append({"article_id": aid, "error": f"stop_reason:{msg.stop_reason}", "answer": None})
                continue
            text = next((blk.text for blk in msg.content if blk.type == "text"), "")
            try:
                ans = json.loads(text)
                row = con.execute("SELECT text FROM article WHERE id=?", (aid,)).fetchone()
                ref = con.execute("SELECT title FROM ref_title_ko WHERE article_id=?", (aid,)).fetchone()
                check({"id": aid, **ans}, row[0], ref[0] if ref else None)
            except (json.JSONDecodeError, SummaryError) as e:
                failures.append({"article_id": aid, "error": str(e), "answer": text})
                continue
            out.write(json.dumps({"id": aid, **ans, "meta": {"model": msg.model, "prompt": PROMPT_VERSION,
                                                              "round": r["n"]}}, ensure_ascii=False) + "\n")
            ok += 1
    with open(d / f"round{r['n']}.failures.jsonl", "w", encoding="utf-8") as f:
        for x in failures:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    r.update({"collected": True, "ok": ok, "failed": len(failures), "usage": usage, "usd": _cost(usage, st.get("model", MODEL))})
    _save_state(d, st)
    if ok and not no_load:  # 작업 DB에도 적재 (다음 prepare가 건너뛰도록)
        n, errs = load_jsonl(args.db, str(out_path), st.get("model", MODEL))
        if errs:
            print("적재 오류:", *errs, sep="\n  ")
    total = sum(x.get("usd", 0) for x in st["rounds"])
    print(f"통과 {ok}건 → {out_path.relative_to(ROOT)}, 실패 {len(failures)}건, "
          f"이번 비용 ${r['usd']} (누적 ${round(total, 2)})")
    if ok:
        per = r["usd"] / max(1, r["count"])
        print(f"기사당 실측 ${per:.4f}")


def cmd_retry(con, name, args):
    """실패분을 검증 오류와 함께 다시 요청. 이전 답이 있으면 대화로 이어 고치게 한다."""
    d = _dir(name)
    st = _state(d)
    r = st["rounds"][-1]
    if not r.get("collected"):
        raise SystemExit("먼저 collect")
    if r["n"] >= MAX_ROUNDS:
        raise SystemExit(f"재요청 {MAX_ROUNDS - 1}번을 넘김. 남은 실패는 사람이 검토한다: round{r['n']}.failures.jsonl")
    fails = [json.loads(x) for x in open(d / f"round{r['n']}.failures.jsonl", encoding="utf-8")]
    retryable = [x for x in fails if not x["error"].startswith("stop_reason:refusal")]
    if not retryable:
        raise SystemExit("재요청할 실패 없음")
    system = system_prompt(con)
    n = r["n"] + 1
    with open(d / f"round{n}.requests.jsonl", "w", encoding="utf-8") as f:
        for x in retryable:
            aid = x["article_id"]
            msgs = [{"role": "user", "content": user_message(con, aid)}]
            if x["answer"]:
                msgs += [{"role": "assistant", "content": x["answer"]},
                         {"role": "user", "content": f"자동 검사에서 거부되었다: {x['error']}\n"
                                                     "원문을 다시 확인해 규칙에 맞게 고친 전체 JSON을 다시 출력하라."}]
            f.write(json.dumps({"custom_id": cid(aid), "article_id": aid,
                                "params": _params(system, msgs, st.get("model", MODEL))},
                               ensure_ascii=False) + "\n")
    st["rounds"].append({"n": n, "requests": f"round{n}.requests.jsonl", "count": len(retryable),
                         "batch_id": None, "prompt_version": PROMPT_VERSION})
    _save_state(d, st)
    print(f"{n}회차 준비: {len(retryable)}건 (거절 {len(fails) - len(retryable)}건은 사람 검토)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sillok.generate")
    ap.add_argument("cmd", choices=["prepare", "submit", "status", "collect", "retry"])
    ap.add_argument("db")
    ap.add_argument("name")
    ap.add_argument("--years", nargs=2, type=int, default=[1592, 1598])
    ap.add_argument("--months", nargs="*", type=int)
    ap.add_argument("--books", nargs="*", default=["wna", "wnb"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", choices=list(MODELS), default="opus")
    ap.add_argument("--ids", nargs="*", help="기사 ID를 직접 지정 (모델 비교용)")
    ap.add_argument("--no-load", action="store_true", help="collect 결과를 DB에 적재하지 않음 (비교용)")
    args = ap.parse_args(argv)
    con = sqlite3.connect(args.db)
    globals()[f"cmd_{args.cmd}"](con, args.name, args)


if __name__ == "__main__":
    sys.exit(main())
