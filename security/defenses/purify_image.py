"""
Adversarial Image Defenses for YOLOv8 Photo Agent

Two defenses against adversarial examples that suppress person detection:

Defense 1 — JPEG compression (purify_jpeg):
    Encode the image with a lossy JPEG codec (default quality=75) and
    decode it back to BGR. DCT quantisation destroys high-frequency
    adversarial perturbations. At ε=8/255 JPEG restores person detection
    (conf≈0.55 > threshold=0.3). At ε=16/255 JPEG also fails (defense
    inversion): the large perturbation mass survives DCT quantisation and
    person detection drops to 0.0 — confirmed by Phase 4 eval results.
    Both JPEG and Gaussian blur are gradient-masking defenses susceptible
    to defense inversion at large ε (Athalye et al. 2018).

Defense 2 — Pre/post-blur divergence detector (detect_adversarial):
    Run YOLO twice: once on the raw image, once on a Gaussian-blurred
    copy. If |conf_raw − conf_blur| > threshold, the confidence shift
    suggests high-frequency adversarial noise is present — flag the
    input as suspected adversarial rather than silently modifying it.
    This is a DETECTION defence (raises an alert) rather than a
    purification defence.

    Rationale for the detector: the §4.4 "defense inversion at ε=16/255"
    phenomenon in the original report is a gradient-masking failure —
    blur shifts the vulnerability rather than removing it. The divergence
    detector turns that same signal into an explicit alarm, confirming
    that the input is adversarial even when blur accidentally "works."

Usage:

    from security.defenses.purify_image import purify_jpeg, detect_adversarial

    # Purification
    clean_bgr = purify_jpeg(adversarial_bgr, quality=75)

    # Detection
    is_adv, conf_raw, conf_blur = detect_adversarial(img_bgr, yolo_model)
    if is_adv:
        raise_alert("Suspected adversarial input")
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ── Defense 1: JPEG compression ───────────────────────────────────────────────

def purify_jpeg(img_bgr: np.ndarray, quality: int = 75) -> np.ndarray:
    """
    Encode img_bgr as JPEG at the given quality level, then decode it back.

    Adversarial perturbations are high-frequency signals; JPEG's DCT
    quantisation step rounds away coefficients below the quantisation
    threshold, stripping the perturbation while preserving the coarse
    structure YOLO uses for detection.

    Args:
        img_bgr  : H×W×3 uint8 BGR image (NumPy array)
        quality  : JPEG quality 0–100 (default 75; lower = more compression)

    Returns:
        Purified H×W×3 uint8 BGR image.
    """
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    ok, encoded = cv2.imencode(".jpg", img_bgr, encode_params)
    if not ok:
        logger.error("JPEG encoding failed; returning original image.")
        return img_bgr
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


# ── Defense 2: Pre/post-blur divergence detector ──────────────────────────────

def _max_person_conf(yolo_model, img_bgr: np.ndarray) -> float:
    """Run YOLO inference and return the max person-class confidence (COCO class 0)."""
    results = yolo_model(img_bgr, verbose=False)
    best = 0.0
    for result in results:
        for box in result.boxes:
            if int(box.cls) == 0:  # person
                best = max(best, float(box.conf))
    return best


def detect_adversarial(
    img_bgr: np.ndarray,
    yolo_model,
    blur_ksize: int = 5,
    threshold: float = 0.3,
) -> tuple[bool, float, float]:
    """
    Detect suspected adversarial input by measuring YOLO confidence divergence
    between the raw image and a Gaussian-blurred copy.

    High-frequency adversarial noise causes YOLO to produce a very different
    confidence on blurred vs. raw input. Clean images show stable confidence
    across the blur (|conf_raw - conf_blur| is small).

    Args:
        img_bgr   : the input image to test
        yolo_model: loaded Ultralytics YOLO model
        blur_ksize: Gaussian blur kernel size (default 5×5, matching Phase 2)
        threshold : divergence threshold for flagging; default 0.3

    Returns:
        (is_adversarial, conf_raw, conf_blur)
        is_adversarial — True if |conf_raw - conf_blur| >= threshold
        conf_raw       — person confidence on original image
        conf_blur      — person confidence on blurred image
    """
    conf_raw = _max_person_conf(yolo_model, img_bgr)

    blurred = cv2.GaussianBlur(img_bgr, (blur_ksize, blur_ksize), 0)
    conf_blur = _max_person_conf(yolo_model, blurred)

    divergence = abs(conf_raw - conf_blur)
    is_adversarial = divergence >= threshold

    if is_adversarial:
        logger.warning(
            "Adversarial input suspected: conf_raw=%.3f, conf_blur=%.3f, "
            "divergence=%.3f >= threshold=%.3f",
            conf_raw, conf_blur, divergence, threshold,
        )
    return (is_adversarial, conf_raw, conf_blur)
