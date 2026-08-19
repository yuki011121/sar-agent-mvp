"""
Adversarial Examples Evaluation Harness

Five phases, all run locally against the YOLOv8m model (no Docker stack needed):
  Phase 1 — Baseline : clean image, no defense → person-detection rate
  Phase 2 — Attack   : PGD adversarial image, no defense → suppression rate
             Tested at three epsilon values: 4/255, 8/255, 16/255
  Phase 3 — Defense (blur)   : PGD + Gaussian 5×5 [weak baseline, gradient masking]
  Phase 4 — Defense (jpeg)   : PGD + JPEG compression q=75 [new]
  Phase 5 — Defense (detect) : PGD + pre/post-blur divergence detector [new]
             For phase 5, "success" = person suppressed AND detector did NOT fire.

NOTE on the "defense inversion at ε=16/255" in phase 3: this is an
obfuscated-gradients failure (Athalye et al. 2018), not a working-range issue.
Blur masks gradients without removing adversarial signal; the phase 5 detector
confirms this by firing at ε=16/255 even when YOLO is fooled differently.

Metric:
  person_detected  = any YOLO box with class "person" and confidence ≥ 0.3
  attack_success   = person NOT detected (mission-critical SAR failure)
  ASR              = fraction of trials where attack succeeded

Usage:
    python eval_adversarial.py --image /path/to/person.jpg
    python eval_adversarial.py --image /path/to/person.jpg --phase 1 2 3 4 5
    python eval_adversarial.py --image /path/to/person.jpg --trials 3
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

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


# ── Differentiable Gaussian blur (for Phase 6 adaptive / EOT attack) ──────────

def _make_gaussian_kernel(ksize: int = 5, sigma: float = 1.0) -> torch.Tensor:
    coords = torch.arange(ksize).float() - ksize // 2
    g = torch.exp(-(coords ** 2) / (2 * sigma ** 2))
    k = g.outer(g)
    k = k / k.sum()
    return k.view(1, 1, ksize, ksize)


def diff_gaussian_blur(x: torch.Tensor) -> torch.Tensor:
    """Differentiable Gaussian blur via F.conv2d — gradients flow through."""
    kernel = _make_gaussian_kernel(5, 1.0).to(x.device).expand(3, 1, 5, 5)
    return F.conv2d(x, kernel, padding=2, groups=3)


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


def apply_defense_blur(img_bgr: np.ndarray) -> np.ndarray:
    """Gaussian blur 5×5 — weak baseline (gradient masking; Guo et al. 2018)."""
    return cv2.GaussianBlur(img_bgr, (5, 5), 0)


def apply_defense_jpeg(img_bgr: np.ndarray, quality: int = 75) -> np.ndarray:
    """JPEG compression q=75 — DCT-based input transformation."""
    from security.defenses.purify_image import purify_jpeg
    return purify_jpeg(img_bgr, quality=quality)


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
                torch_model, img_tensor, eps, n_steps=n_steps,
                step_size=DEFAULT_STEP_SIZE, random_start=True,
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


def _run_purification_defense(
    yolo, torch_model, img_bgr: np.ndarray, n_trials: int,
    n_steps: int, defense_fn, phase_label: str,
) -> dict:
    """Generic runner for purification defenses (blur, jpeg)."""
    img_tensor, _ = preprocess(img_bgr)
    trials = []
    for eps in EPSILON_VALUES:
        print(f"\n  ε = {eps:.4f}  ({eps*255:.1f}/255)")
        for i in range(1, n_trials + 1):
            adv_tensor, clean_conf, adv_conf = pgd_attack(
                torch_model, img_tensor, eps, n_steps=n_steps,
                step_size=DEFAULT_STEP_SIZE, random_start=True,
            )
            adv_bgr = tensor_to_bgr(adv_tensor)
            defended_bgr = defense_fn(adv_bgr)
            result = detect_persons(yolo, defended_bgr)
            attack_bypasses = not result["person_detected"]
            trials.append({
                "trial": i, "epsilon": eps, "n_steps": n_steps,
                "success": attack_bypasses,
                "person_detected": result["person_detected"],
                "clean_conf": clean_conf, "adv_conf": adv_conf,
                "defended_person_conf": result["max_person_conf"],
            })
            status = "RECOVERED" if result["person_detected"] else "still suppressed"
            print(f"    Trial {i}: {status:<20} defended_conf={result['max_person_conf']:.3f}")
    asr = calculate_asr(trials)
    print(f"\n  Defense bypass rate: {asr:.1%}")
    return {"phase": phase_label, "trials": trials, "asr": asr}


def run_phase3_defense(
    yolo, torch_model, img_bgr: np.ndarray, n_trials: int,
    n_steps: int = DEFAULT_PGD_STEPS,
) -> dict:
    attack_label = f"PGD ({n_steps} steps)" if n_steps > 1 else "FGSM (1 step)"
    print(f"\n{'=' * 70}")
    print(f"PHASE 3: Defense ({attack_label} + Gaussian blur 5×5) [weak baseline]")
    print(f"  NOTE: Gaussian blur is a gradient-masking defense (Guo et al. 2018);")
    print(f"  defense inversion at ε=16/255 is an obfuscated-gradients failure")
    print(f"  (Athalye et al. 2018), NOT a working-range limitation.")
    print(f"Epsilon values: {[f'{e*255:.0f}/255' for e in EPSILON_VALUES]}  |  Trials: {n_trials}")
    print("=" * 70)
    return _run_purification_defense(
        yolo, torch_model, img_bgr, n_trials, n_steps,
        apply_defense_blur,
        f"Phase 3: Defense ({attack_label} + Gaussian blur, weak baseline)",
    )


def run_phase4_jpeg(
    yolo, torch_model, img_bgr: np.ndarray, n_trials: int,
    n_steps: int = DEFAULT_PGD_STEPS,
) -> dict:
    attack_label = f"PGD ({n_steps} steps)" if n_steps > 1 else "FGSM (1 step)"
    print(f"\n{'=' * 70}")
    print(f"PHASE 4: Defense ({attack_label} + JPEG compression q=75)")
    print(f"Epsilon values: {[f'{e*255:.0f}/255' for e in EPSILON_VALUES]}  |  Trials: {n_trials}")
    print("=" * 70)
    return _run_purification_defense(
        yolo, torch_model, img_bgr, n_trials, n_steps,
        apply_defense_jpeg,
        f"Phase 4: Defense ({attack_label} + JPEG q=75)",
    )


def run_phase5_detect(
    yolo, torch_model, img_bgr: np.ndarray, n_trials: int,
    n_steps: int = DEFAULT_PGD_STEPS,
    divergence_threshold: float = 0.3,
) -> dict:
    """
    Phase 5: pre/post-blur divergence detector.
    'success' (from attacker's perspective) = person suppressed AND detector did NOT fire.
    'detector_fired' is recorded separately so we can compute detection rate.
    """
    from security.defenses.purify_image import detect_adversarial as _detect_adv
    attack_label = f"PGD ({n_steps} steps)" if n_steps > 1 else "FGSM (1 step)"
    print(f"\n{'=' * 70}")
    print(f"PHASE 5: Detection defense ({attack_label} + divergence detector, threshold={divergence_threshold})")
    print(f"  'Attack success' = person suppressed AND detector did NOT fire.")
    print(f"Epsilon values: {[f'{e*255:.0f}/255' for e in EPSILON_VALUES]}  |  Trials: {n_trials}")
    print("=" * 70)
    img_tensor, _ = preprocess(img_bgr)
    trials = []
    for eps in EPSILON_VALUES:
        print(f"\n  ε = {eps:.4f}  ({eps*255:.1f}/255)")
        for i in range(1, n_trials + 1):
            adv_tensor, clean_conf, adv_conf = pgd_attack(
                torch_model, img_tensor, eps, n_steps=n_steps,
                step_size=DEFAULT_STEP_SIZE, random_start=True,
            )
            adv_bgr = tensor_to_bgr(adv_tensor)
            result_raw = detect_persons(yolo, adv_bgr)
            is_adv, c_raw, c_blur = _detect_adv(
                adv_bgr, yolo, threshold=divergence_threshold
            )
            person_suppressed = not result_raw["person_detected"]
            attack_success = person_suppressed and not is_adv  # evaded both
            trials.append({
                "trial": i, "epsilon": eps, "n_steps": n_steps,
                "success": attack_success,
                "person_detected": result_raw["person_detected"],
                "detector_fired": is_adv,
                "conf_raw": c_raw, "conf_blur": c_blur,
                "divergence": abs(c_raw - c_blur),
                "clean_conf": clean_conf, "adv_conf": adv_conf,
                "yolo_person_conf": result_raw["max_person_conf"],
            })
            det_status = "DETECTOR FIRED" if is_adv else "detector silent"
            yolo_status = "suppressed" if person_suppressed else "detected"
            print(
                f"    Trial {i}: YOLO={yolo_status:<10} {det_status:<18}"
                f" divergence={abs(c_raw - c_blur):.3f}"
            )
    asr = calculate_asr(trials)
    det_rate = sum(1 for t in trials if t["detector_fired"]) / len(trials) if trials else 0.0
    print(f"\n  Attacker full-bypass rate (suppress + evade detector): {asr:.1%}")
    print(f"  Detector fire rate: {det_rate:.1%}")
    return {
        "phase": f"Phase 5: Detection defense ({attack_label} + divergence detector)",
        "trials": trials, "asr": asr, "detector_fire_rate": det_rate,
    }


def run_phase6_adaptive_blur(
    yolo, torch_model, img_bgr: np.ndarray, n_trials: int,
    n_steps: int = DEFAULT_PGD_STEPS,
) -> dict:
    """
    Phase 6: Adaptive attack (EOT) — PGD gradients flow through differentiable
    Gaussian blur. Tests whether Blur is a true defense or gradient masking.

    Attack: optimise δ to suppress person confidence AFTER blur is applied.
    Defense: apply the same Gaussian blur before YOLO inference.
    Success: person still not detected after blur defense.

    If ASR here is higher than Phase 3 (non-adaptive) at the same ε, that
    confirms Phase 3's 'blocked' result was gradient masking, not robustness.
    """
    attack_label = f"PGD ({n_steps} steps)" if n_steps > 1 else "FGSM (1 step)"
    print(f"\n{'=' * 70}")
    print(f"PHASE 6: Adaptive attack against Gaussian blur (EOT)")
    print(f"  Gradients flow through differentiable blur in PGD loop.")
    print(f"  Higher ASR than Phase 3 confirms gradient-masking, not robustness.")
    print(f"Epsilon values: {[f'{e*255:.0f}/255' for e in EPSILON_VALUES]}  |  Trials: {n_trials}")
    print("=" * 70)

    img_tensor, _ = preprocess(img_bgr)
    trials = []

    for eps in EPSILON_VALUES:
        print(f"\n  ε = {eps:.4f}  ({eps*255:.1f}/255)")
        for i in range(1, n_trials + 1):
            # Attack: PGD with differentiable blur in the gradient path
            adv_tensor, clean_conf, adv_conf = pgd_attack(
                torch_model, img_tensor, eps, n_steps=n_steps,
                step_size=DEFAULT_STEP_SIZE, random_start=True,
                transform_fn=diff_gaussian_blur,
            )
            adv_bgr = tensor_to_bgr(adv_tensor)
            # Defense: apply same Gaussian blur before YOLO
            defended_bgr = apply_defense_blur(adv_bgr)
            result = detect_persons(yolo, defended_bgr)
            attack_success = not result["person_detected"]
            trials.append({
                "trial": i, "epsilon": eps, "n_steps": n_steps,
                "success": attack_success,
                "person_detected": result["person_detected"],
                "clean_conf": clean_conf, "adv_conf": adv_conf,
                "defended_person_conf": result["max_person_conf"],
            })
            status = "*** ADAPTIVE BYPASS ***" if attack_success else "defended"
            print(
                f"    Trial {i}: {status:<24} "
                f"grad_conf {clean_conf:.3f}→{adv_conf:.3f}  "
                f"defended_conf={result['max_person_conf']:.3f}"
            )

    asr = calculate_asr(trials)
    print(f"\n  Adaptive-attack bypass rate: {asr:.1%}")
    return {
        "phase": f"Phase 6: Adaptive attack vs blur ({attack_label}, EOT)",
        "trials": trials, "asr": asr,
    }


# ── Full evaluation ───────────────────────────────────────────────────────────

def run_evaluation(
    image_path: str,
    n_trials: int = 5,
    phases: list[int] | None = None,
    n_steps: int = DEFAULT_PGD_STEPS,
) -> dict:
    active_phases = phases or [1, 2, 3, 4, 5, 6]

    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        print(f"[!] Could not read image: {image_path}")
        sys.exit(1)

    attack_label = f"PGD ({n_steps} steps, step={DEFAULT_STEP_SIZE*255:.0f}/255)" if n_steps > 1 else "FGSM (1 step)"

    print("\n" + "=" * 70)
    print("SAR ADVERSARIAL EXAMPLES — EVALUATION")
    print(f"Image      : {image_path}")
    print(f"Model      : yolov8m.pt  (COCO person class 0)")
    print(f"Attack     : {attack_label} — person-confidence suppression")
    print(f"             random_start=True → each trial is an independent R-PGD sample")
    print(f"Defenses   : blur (weak) | jpeg q=75 | divergence detector | adaptive-blur (EOT)")
    print(f"Epsilons   : {[f'{e*255:.0f}/255' for e in EPSILON_VALUES]}")
    print(f"Trials     : {n_trials} per epsilon per phase")
    print("=" * 70)

    print("\n[*] Loading YOLOv8m…")
    yolo, torch_model = load_model()

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
            "defenses": {
                "phase3": "Gaussian blur 5x5 (weak baseline, gradient masking)",
                "phase4": "JPEG compression q=75",
                "phase5": "Pre/post-blur divergence detector (threshold=0.3)",
                "phase6": "Adaptive attack (EOT) against Gaussian blur — PGD gradients through diff blur",
            },
            "random_start": True,
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

    if 4 in active_phases:
        phase = run_phase4_jpeg(yolo, torch_model, img_bgr, n_trials, n_steps=n_steps)
        all_results["phases"].append(phase)

    if 5 in active_phases:
        phase = run_phase5_detect(yolo, torch_model, img_bgr, n_trials, n_steps=n_steps)
        all_results["phases"].append(phase)

    if 6 in active_phases:
        phase = run_phase6_adaptive_blur(yolo, torch_model, img_bgr, n_trials, n_steps=n_steps)
        all_results["phases"].append(phase)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    summary = {}
    for ph in all_results["phases"]:
        key = ph["phase"]
        det_rate = ph.get("detector_fire_rate")
        summary[key] = {"asr": ph["asr"]}
        det_str = f"  det_rate={det_rate:.1%}" if det_rate is not None else ""
        print(f"  {key[:58]:<58}  ASR={ph['asr']:.1%}{det_str}")
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
        "--phase", type=int, choices=[1, 2, 3, 4, 5, 6], nargs="+",
        help="Which phases to run (default: 1 2 3 4 5 6)",
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
