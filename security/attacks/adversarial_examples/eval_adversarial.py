"""
Adversarial Examples Evaluation Harness

Three phases, all run locally against the YOLOv8m model (no Docker container needed):
  Phase 1 — Baseline : clean image, no defense → establishes person-detection rate
  Phase 2 — Attack   : FGSM adversarial image, no defense → measures suppression rate
             Tested at three epsilon values: 4/255, 8/255, 16/255
  Phase 3 — Defense  : FGSM adversarial + Gaussian smoothing → measures recovery rate

Metric:
  person_detected  = any YOLO box with class "person" and confidence ≥ 0.3
  attack_success   = person NOT detected (mission-critical failure in SAR)
  ASR              = fraction of trials where attack succeeded

Usage:
    python eval_adversarial.py --image /path/to/person.jpg
    python eval_adversarial.py --image /path/to/person.jpg --phase 1 2
    python eval_adversarial.py --image /path/to/person.jpg --trials 3
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from security.attacks.adversarial_examples.generate_adversarial import (
    load_model,
    preprocess,
    pgd_attack,
    tensor_to_bgr,
    CONF_THRESHOLD,
)
from security.evaluation.metrics import calculate_asr, save_results

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "adversarial_examples"
EPSILON_VALUES = [4 / 255, 8 / 255, 16 / 255]
DEFAULT_PGD_STEPS = 20
DEFAULT_STEP_SIZE = 2 / 255


# ── Detection helpers ─────────────────────────────────────────────────────────

def detect_persons(yolo, img_bgr: np.ndarray) -> dict:
    """Run YOLO inference on a BGR numpy image; return detection summary."""
    results = yolo(img_bgr, verbose=False)
    detections = []
    for r in results:
        for box in r.boxes:
            detections.append({
                "class": yolo.names[int(box.cls)],
                "confidence": float(box.conf),
            })

    persons = [
        d for d in detections
        if d["class"] == "person" and d["confidence"] >= CONF_THRESHOLD
    ]
    max_conf = max((d["confidence"] for d in persons), default=0.0)
    return {
        "person_detected": len(persons) > 0,
        "person_count": len(persons),
        "max_person_conf": max_conf,
        "all_detections": detections,
    }


def apply_defense(img_bgr: np.ndarray) -> np.ndarray:
    """Gaussian smoothing — attenuates high-frequency adversarial perturbations."""
    return cv2.GaussianBlur(img_bgr, (5, 5), 0)


# ── Phase runners ─────────────────────────────────────────────────────────────

def run_phase1_baseline(yolo, img_bgr: np.ndarray, n_trials: int) -> dict:
    print(f"\n{'=' * 70}")
    print("PHASE 1: Baseline (clean image, no defense)")
    print(f"Trials: {n_trials}")
    print("=" * 70)

    trials = []
    for i in range(1, n_trials + 1):
        result = detect_persons(yolo, img_bgr)
        attack_success = not result["person_detected"]
        trials.append({
            "trial": i,
            "epsilon": None,
            "success": attack_success,
            "person_detected": result["person_detected"],
            "max_person_conf": result["max_person_conf"],
        })
        status = "detected" if result["person_detected"] else "NOT DETECTED"
        print(f"  Trial {i}: person {status} (conf={result['max_person_conf']:.3f})")

    asr = calculate_asr(trials)
    print(f"\n  Baseline miss rate: {asr:.1%}  (should be ~0% on a valid test image)")
    return {"phase": "Phase 1: Baseline (clean, no defense)", "trials": trials, "asr": asr}


def run_phase2_attack(
    yolo, torch_model, img_bgr: np.ndarray, n_trials: int,
    n_steps: int = DEFAULT_PGD_STEPS,
) -> dict:
    attack_label = f"PGD ({n_steps} steps)" if n_steps > 1 else "FGSM (1 step)"
    print(f"\n{'=' * 70}")
    print(f"PHASE 2: Attack ({attack_label}, no defense)")
    print(f"Epsilon values: {[f'{e*255:.0f}/255' for e in EPSILON_VALUES]}  |  Trials per epsilon: {n_trials}")
    print("=" * 70)

    img_tensor, _ = preprocess(img_bgr)
    trials = []

    for eps in EPSILON_VALUES:
        print(f"\n  ε = {eps:.4f}  ({eps*255:.1f}/255)  steps={n_steps}  step_size={DEFAULT_STEP_SIZE*255:.1f}/255")
        for i in range(1, n_trials + 1):
            adv_tensor, clean_conf, adv_conf = pgd_attack(
                torch_model, img_tensor, eps, n_steps=n_steps, step_size=DEFAULT_STEP_SIZE
            )
            adv_bgr = tensor_to_bgr(adv_tensor)
            result = detect_persons(yolo, adv_bgr)

            attack_success = not result["person_detected"]
            trials.append({
                "trial": i,
                "epsilon": eps,
                "n_steps": n_steps,
                "success": attack_success,
                "person_detected": result["person_detected"],
                "clean_conf": clean_conf,
                "adv_conf": adv_conf,
                "yolo_person_conf": result["max_person_conf"],
            })
            outcome = "*** ATTACK SUCCESS ***" if attack_success else "defended"
            print(
                f"    Trial {i}: {outcome:<22} "
                f"grad_conf {clean_conf:.3f}→{adv_conf:.3f}  "
                f"yolo_conf={result['max_person_conf']:.3f}"
            )

    asr = calculate_asr(trials)
    print(f"\n  Overall attack ASR (person suppressed): {asr:.1%}")
    return {
        "phase": f"Phase 2: Attack ({attack_label}, no defense)",
        "trials": trials, "asr": asr,
    }


def run_phase3_defense(
    yolo, torch_model, img_bgr: np.ndarray, n_trials: int,
    n_steps: int = DEFAULT_PGD_STEPS,
) -> dict:
    attack_label = f"PGD ({n_steps} steps)" if n_steps > 1 else "FGSM (1 step)"
    print(f"\n{'=' * 70}")
    print(f"PHASE 3: Defense ({attack_label} + Gaussian smoothing 5×5)")
    print(f"Epsilon values: {[f'{e*255:.0f}/255' for e in EPSILON_VALUES]}  |  Trials per epsilon: {n_trials}")
    print("=" * 70)

    img_tensor, _ = preprocess(img_bgr)
    trials = []

    for eps in EPSILON_VALUES:
        print(f"\n  ε = {eps:.4f}  ({eps*255:.1f}/255)")
        for i in range(1, n_trials + 1):
            adv_tensor, clean_conf, adv_conf = pgd_attack(
                torch_model, img_tensor, eps, n_steps=n_steps, step_size=DEFAULT_STEP_SIZE
            )
            adv_bgr = tensor_to_bgr(adv_tensor)
            defended_bgr = apply_defense(adv_bgr)
            result = detect_persons(yolo, defended_bgr)

            attack_bypasses_defense = not result["person_detected"]
            trials.append({
                "trial": i,
                "epsilon": eps,
                "n_steps": n_steps,
                "success": attack_bypasses_defense,
                "person_detected": result["person_detected"],
                "clean_conf": clean_conf,
                "adv_conf": adv_conf,
                "defended_person_conf": result["max_person_conf"],
            })
            status = "person RECOVERED" if result["person_detected"] else "still suppressed"
            print(
                f"    Trial {i}: {status:<22} "
                f"defended_conf={result['max_person_conf']:.3f}"
            )

    asr = calculate_asr(trials)
    print(f"\n  Defense bypass rate (attack still succeeds after blur): {asr:.1%}")
    return {
        "phase": f"Phase 3: Defense ({attack_label} + Gaussian blur)",
        "trials": trials, "asr": asr,
    }


# ── Full evaluation ───────────────────────────────────────────────────────────

def run_evaluation(
    image_path: str,
    n_trials: int = 5,
    phases: list[int] | None = None,
    n_steps: int = DEFAULT_PGD_STEPS,
) -> dict:
    active_phases = phases or [1, 2, 3]

    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        print(f"[!] Could not read image: {image_path}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("SAR ADVERSARIAL EXAMPLES — EVALUATION")
    print(f"Image      : {image_path}")
    attack_label = f"PGD ({n_steps} steps, step={DEFAULT_STEP_SIZE*255:.0f}/255)" if n_steps > 1 else "FGSM (1 step)"
    print(f"Model      : yolov8m.pt  (COCO person class 0)")
    print(f"Attack     : {attack_label} — person-confidence suppression")
    print(f"Defense    : Gaussian blur (5×5, σ=0)")
    print(f"Epsilons   : {[f'{e*255:.0f}/255' for e in EPSILON_VALUES]}")
    print(f"Trials     : {n_trials} per epsilon")
    print("=" * 70)

    print("\n[*] Loading YOLOv8m…")
    yolo, torch_model = load_model()

    # Sanity check: clean image must contain a detectable person
    clean_check = detect_persons(yolo, img_bgr)
    if not clean_check["person_detected"]:
        print(
            "\n[!] ABORT: No person detected in the clean image (conf ≥ 0.3).\n"
            "    Provide an image where YOLOv8 detects at least one person."
        )
        sys.exit(1)
    print(f"[*] Person confirmed in clean image (max_conf={clean_check['max_person_conf']:.3f})")

    all_results: dict = {
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "image": image_path,
            "model": "yolov8m.pt",
            "attack": attack_label,
            "defense": "Gaussian blur (5x5, sigma=0)",
            "epsilon_values": EPSILON_VALUES,
            "n_steps": n_steps,
            "step_size": DEFAULT_STEP_SIZE,
            "n_trials_per_epsilon": n_trials,
            "conf_threshold": CONF_THRESHOLD,
        },
        "phases": [],
        "summary": {},
    }

    if 1 in active_phases:
        phase = run_phase1_baseline(yolo, img_bgr, n_trials)
        all_results["phases"].append(phase)

    if 2 in active_phases:
        phase = run_phase2_attack(yolo, torch_model, img_bgr, n_trials, n_steps=n_steps)
        all_results["phases"].append(phase)

    if 3 in active_phases:
        phase = run_phase3_defense(yolo, torch_model, img_bgr, n_trials, n_steps=n_steps)
        all_results["phases"].append(phase)

    # Summary table
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    summary = {}
    for ph in all_results["phases"]:
        key = ph["phase"]
        summary[key] = {"asr": ph["asr"]}
        print(f"  {key[:60]:<60}  ASR={ph['asr']:.1%}")
    all_results["summary"] = summary

    fname = f"eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    save_results(all_results, str(RESULTS_DIR), fname)
    return all_results


def main():
    parser = argparse.ArgumentParser(description="SAR adversarial examples evaluation (YOLOv8m)")
    parser.add_argument(
        "--image", required=True,
        help="Path to source image containing a visible person",
    )
    parser.add_argument(
        "--trials", type=int, default=5,
        help="Trials per epsilon value (default 5)",
    )
    parser.add_argument(
        "--phase", type=int, choices=[1, 2, 3], nargs="+",
        help="Which phases to run (default: 1 2 3)",
    )
    parser.add_argument(
        "--steps", type=int, default=DEFAULT_PGD_STEPS,
        help=f"PGD iterations (default: {DEFAULT_PGD_STEPS}; use 1 for single-step FGSM)",
    )
    args = parser.parse_args()

    run_evaluation(
        image_path=args.image, n_trials=args.trials,
        phases=args.phase, n_steps=args.steps,
    )


if __name__ == "__main__":
    main()
