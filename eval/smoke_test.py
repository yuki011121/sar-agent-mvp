# eval/smoke_test.py
import argparse, json, os, time, uuid, sys, pathlib
import requests
from .agent_client import call_agent  # relative import from eval package

def read_jsonl(p):
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="eval/golden.jsonl")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--latency_warn_ms", type=int, default=15000)  # 15s
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
            "error": None if passed else repr(last_err),
        })

        print(f"[{i}/{total}] {'OK' if passed else 'FAIL'} {elapsed_ms} ms")

    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    slow_cnt = sum(1 for r in results if r["slow"])
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# Agent smoke test\n")
        f.write(f"- Total: **{total}**  |  Passed: **{ok}**  |  Failed: **{failures}**  |  Slow(>{args.latency_warn_ms} ms): **{slow_cnt}**\n\n")
        f.write("| # | Latency (ms) | Slow | Error |\n|---:|---:|:---:|---|\n")
        for r in results:
            f.write(f"| {r['idx']} | {r['latency_ms']} | {'✅' if r['slow'] else ''} | {r['error'] or ''} |\n")

    if failures > 0:
        print(f"Failures: {failures}. See {out_path}.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
