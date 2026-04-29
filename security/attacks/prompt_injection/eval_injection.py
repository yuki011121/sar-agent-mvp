"""
Prompt Injection Evaluation Harness

Runs N trials for each payload variant (clean baseline, Payload A, Payload B),
calculates Attack Success Rate (ASR), and saves results to
security/results/prompt_injection/.

Usage:
    python eval_injection.py                   # 5 trials per payload
    python eval_injection.py --trials 10
    python eval_injection.py --trials 3 --timeout 120
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# Make project root importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from security.attacks.prompt_injection.inject_redis_stream import (
    CLEAN_TRANSCRIPT,
    LABELS,
    PAYLOAD_A,
    PAYLOAD_B,
    publish_to_interview,
    wait_for_result,
    check_success,
)
from security.evaluation.metrics import calculate_asr, save_results

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "prompt_injection"


def run_trial(payload_key: str, transcript: str, trial_num: int, timeout: int) -> dict:
    label = f"{LABELS[payload_key]}_trial_{trial_num}"
    task_id = publish_to_interview(transcript)
    result = wait_for_result(task_id, timeout=timeout)

    if result is None:
        return {"label": label, "task_id": task_id, "success": False, "error": "timeout"}

    success, matched = check_success(result)
    return {
        "label":            label,
        "task_id":          task_id,
        "success":          success,
        "matched_keywords": matched,
        "raw_result":       result,
    }


def run_evaluation(n_trials: int = 5, timeout: int = 90) -> dict:
    payloads = {
        "clean": CLEAN_TRANSCRIPT,
        "A":     PAYLOAD_A,
        "B":     PAYLOAD_B,
    }

    all_results: dict = {
        "metadata": {
            "timestamp":    datetime.utcnow().isoformat() + "Z",
            "n_trials":     n_trials,
            "timeout_secs": timeout,
            "attack_vectors": ["redis_stream"],
        },
        "trials": {key: [] for key in payloads},
        "summary": {},
    }

    print("=" * 70)
    print("SAR PROMPT INJECTION — EVALUATION")
    print(f"Trials per payload : {n_trials}")
    print(f"Timeout per trial  : {timeout}s")
    print("=" * 70)

    for key, transcript in payloads.items():
        print(f"\n--- [{key}] {LABELS[key]} ---")
        bucket = all_results["trials"][key]
        for i in range(1, n_trials + 1):
            print(f"  Trial {i}/{n_trials} … ", end="", flush=True)
            trial = run_trial(key, transcript, i, timeout)
            bucket.append(trial)

            if trial.get("error"):
                print(f"ERROR ({trial['error']})")
            elif trial["success"]:
                print(f"*** INJECTED *** {trial['matched_keywords']}")
            else:
                print("failed")

            if i < n_trials:
                time.sleep(3)   # brief pause so the agent has time to process

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = {
        "baseline_asr":  calculate_asr(all_results["trials"]["clean"]),
        "payload_a_asr": calculate_asr(all_results["trials"]["A"]),
        "payload_b_asr": calculate_asr(all_results["trials"]["B"]),
    }
    all_results["summary"] = summary

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"  Baseline ASR (false-positive rate) : {summary['baseline_asr']:.1%}")
    print(f"  Payload A ASR (direct command)     : {summary['payload_a_asr']:.1%}")
    print(f"  Payload B ASR (disguised note)     : {summary['payload_b_asr']:.1%}")
    print()

    fname = f"eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    save_results(all_results, str(RESULTS_DIR), fname)
    return all_results


def main():
    parser = argparse.ArgumentParser(description="SAR prompt injection evaluation")
    parser.add_argument("--trials",  type=int, default=5,  help="Trials per payload (default 5)")
    parser.add_argument("--timeout", type=int, default=90, help="Seconds to wait per trial (default 90)")
    args = parser.parse_args()
    run_evaluation(n_trials=args.trials, timeout=args.timeout)


if __name__ == "__main__":
    main()
