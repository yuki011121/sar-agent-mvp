# eval/smoke_test.py
import argparse, json, os, time, uuid, sys, pathlib, re
import requests
from .agent_client import call_agent  # relative import from eval package

BANNED_PATTERNS = [
    r"\bAs an AI (?:assistant|language model)\b",
    r"\bI (?:cannot|can't) (?:assist|help) with that\b",
    r"\bI (?:don'?t|do not) have (?:access|the ability) to browse\b",
    r"\bI am unable to\b",
]
_BANNED_RES = [re.compile(p, re.IGNORECASE) for p in BANNED_PATTERNS]

def read_jsonl(p):
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def check_quality(text: str, min_chars: int):
    reasons = []
    if len(text.strip()) < min_chars:
        reasons.append(f"too short (<{min_chars} chars)")
    for rx in _BANNED_RES:
        if rx.search(text):
            reasons.append(f"banned:{rx.pattern}")
            break
    return (len(reasons) == 0, reasons)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="eval/golden.jsonl")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--latency_warn_ms", type=int, default=15000)  # 15s soft cap
    ap.add_argument("--max_slow", type=int, default=2, help="fail if more than this many prompts exceed latency_warn_ms")
    ap.add_argument("--min_chars", type=int, default=40, help="minimum characters required for a response")
    args = ap.parse_args()

    out_dir = pathlib.Path("eval/out"); out_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:8]
    out_path = out_dir / f"smoke_{run_id}.jsonl"
    summary_path = out_dir / f"summary_{run_id}.md"

    session = requests.Session()
    rows = list(read_jsonl(args.dataset))[: args.limit]
    total = len(rows); ok = 0; failures = 0
    results = []

    for i, row in enumerate(rows, 1):
        q = row.get("query", "")
        ctx = row.get("context", "")
        attempt = 0
        last_err = None
        resp_text = ""
        start = time.perf_counter_ns()

        while attempt <= args.retries:
            try:
                resp_text = call_agent(q, ctx, session=session)
                break
            except Exception as e:
                last_err = e
                time.sleep(0.5 * (2**attempt))
                attempt += 1

        elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)
        passed = bool(resp_text and isinstance(resp_text, str))
        slow = elapsed_ms > args.latency_warn_ms

        quality_ok, quality_reasons = (False, ["no response"]) if not passed else check_quality(resp_text, args.min_chars)

        if passed:
            ok += 1
        else:
            failures += 1

        results.append({
            "idx": i,
            "query": q,
            "response": resp_text if passed else "",
            "latency_ms": elapsed_ms,
            "slow": slow,
            "quality_ok": quality_ok,
            "quality_reasons": [] if quality_ok else quality_reasons,
            "error": None if passed else repr(last_err),
        })

        status = "OK" if (passed and quality_ok) else "FAIL"
        print(f"[{i}/{total}] {status} {elapsed_ms} ms" + ("" if quality_ok else f"  {'; '.join(quality_reasons)}"))

    # write artifacts
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    slow_cnt = sum(1 for r in results if r["slow"])
    qual_fail_cnt = sum(1 for r in results if not r["quality_ok"])
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# Agent smoke test\n")
        f.write(f"- Total: **{total}**  |  Passed(no error): **{ok}**  |  Empty/Error: **{failures}**\n")
        f.write(f"- Slow(>{args.latency_warn_ms} ms): **{slow_cnt}** (max allowed {args.max_slow})\n")
        f.write(f"- Quality failures: **{qual_fail_cnt}** (min chars {args.min_chars}; banned {len(BANNED_PATTERNS)} patterns)\n\n")
        f.write("| # | Latency (ms) | Slow | Quality OK | Reasons |\n|---:|---:|:---:|:---:|---|\n")
        for r in results:
            f.write(f"| {r['idx']} | {r['latency_ms']} | {'✅' if r['slow'] else ''} | {'✅' if r['quality_ok'] else ''} | {'; '.join(r['quality_reasons'])} |\n")

    # gating rules:
    gate_fail = (failures > 0) or (qual_fail_cnt > 0) or (slow_cnt > args.max_slow)
    if gate_fail:
        print(f"Failing CI. Empty/Error: {failures}, Quality failures: {qual_fail_cnt}, Slow: {slow_cnt}>{args.max_slow}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
