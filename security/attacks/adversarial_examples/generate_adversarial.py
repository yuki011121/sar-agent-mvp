"""
FGSM adversarial attack against YOLOv8m — suppresses "person" class detection.

Fast Gradient Sign Method (FGSM) computes the gradient of the person-class
confidence score w.r.t. the input image, then perturbs the image in the
direction that minimises that confidence.

Usage:
    python generate_adversarial.py --image /path/to/person.jpg
    python generate_adversarial.py --image /path/to/person.jpg --epsilon 0.031 --output-dir /tmp/adv
"""

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.data.augment import LetterBox

YOLO_MODEL = "yolov8m.pt"
INPUT_SIZE = 640
COCO_PERSON_IDX = 0  # "person" is class 0 in COCO80
COCO_NC = 80         # number of COCO classes
CONF_THRESHOLD = 0.3


# ── Model + preprocessing ─────────────────────────────────────────────────────

def load_model(model_path: str = YOLO_MODEL) -> tuple:
    yolo = YOLO(model_path)
    torch_model = yolo.model
    torch_model.eval()
    return yolo, torch_model


def preprocess(image_bgr: np.ndarray) -> tuple[torch.Tensor, np.ndarray]:
    """
    Letterbox + normalise to [1, 3, 640, 640] float tensor.
    Returns (tensor, letterboxed_bgr) — the letterboxed image is returned so
    the adversarial result can be saved directly without un-padding.
    """
    lb = LetterBox(new_shape=(INPUT_SIZE, INPUT_SIZE))
    img_lb = lb(image=image_bgr)              # 640×640 BGR uint8
    img_rgb = img_lb[..., ::-1].copy()        # BGR → RGB, contiguous
    img_float = img_rgb.astype(np.float32) / 255.0
    tensor = torch.from_numpy(img_float).permute(2, 0, 1).unsqueeze(0)  # [1,3,H,W]
    return tensor, img_lb


def tensor_to_bgr(tensor: torch.Tensor) -> np.ndarray:
    """[1, 3, H, W] float [0, 1] → HWC BGR uint8"""
    arr = tensor.squeeze(0).detach().cpu().clamp(0.0, 1.0).numpy()  # [3,H,W]
    arr = (arr * 255).round().astype(np.uint8)
    arr = arr.transpose(1, 2, 0)   # HWC RGB
    return arr[..., ::-1].copy()   # RGB → BGR


# ── Gradient-based person confidence ─────────────────────────────────────────

def _get_person_confidence_train(torch_model, img_tensor: torch.Tensor) -> torch.Tensor:
    """
    Compute max person-class confidence in **training mode**.

    In eval mode, ultralytics caches `self.anchors` as an inference_mode tensor
    that cannot enter the autograd graph. Training mode returns a dict:
      {
        'boxes':  [batch, 64, 8400]   — raw DFL box regression logits
        'scores': [batch, 80, 8400]   — raw class logits (pre-sigmoid)
        'feats':  list of backbone feature maps
      }
    Person is COCO class 0 → scores[:, 0, :].
    """
    raw = torch_model(img_tensor)           # dict in training mode
    person_logits = raw["scores"][0, COCO_PERSON_IDX, :]  # [8400]
    return person_logits.sigmoid().max()


# ── FGSM / PGD attacks ───────────────────────────────────────────────────────

def fgsm_attack(
    torch_model,
    img_tensor: torch.Tensor,
    epsilon: float,
) -> tuple[torch.Tensor, float, float]:
    """
    Single-step FGSM targeting person suppression.
    Convenience wrapper around pgd_attack with n_steps=1.
    """
    return pgd_attack(torch_model, img_tensor, epsilon, n_steps=1, step_size=epsilon)


def pgd_attack(
    torch_model,
    img_tensor: torch.Tensor,
    epsilon: float,
    n_steps: int = 20,
    step_size: float = 2 / 255,
) -> tuple[torch.Tensor, float, float]:
    """
    Projected Gradient Descent (I-FGSM) targeting person suppression.

    Each iteration:
      1. One step of gradient descent on max person confidence (training mode).
      2. Project back into the ε-ball around the original image.
      3. Clip to [0, 1].

    Uses training mode to avoid inference_mode tensor restriction in ultralytics.

    Returns:
        adversarial_tensor  — [1, 3, 640, 640] float, clamped to [0, 1]
        clean_conf          — training-mode person confidence before attack
        adv_conf            — training-mode person confidence after attack
    """
    torch_model.train()

    with torch.no_grad():
        clean_conf = _get_person_confidence_train(torch_model, img_tensor).item()

    img_orig = img_tensor.clone()
    img_adv = img_tensor.clone()

    for _ in range(n_steps):
        img_adv = img_adv.detach().requires_grad_(True)
        with torch.enable_grad():
            person_conf = _get_person_confidence_train(torch_model, img_adv)
            person_conf.backward()

        # Gradient descent step (suppress person confidence)
        img_adv = img_adv.detach() - step_size * img_adv.grad.sign()

        # Project back to ε-ball around original image
        img_adv = torch.max(torch.min(img_adv, img_orig + epsilon), img_orig - epsilon)
        img_adv = img_adv.clamp(0.0, 1.0)

    with torch.no_grad():
        adv_conf = _get_person_confidence_train(torch_model, img_adv).item()

    torch_model.eval()
    return img_adv, clean_conf, adv_conf


# ── Public entry point ────────────────────────────────────────────────────────

def run(image_path: str, epsilon: float = 8 / 255, output_dir: str | None = None) -> str:
    """
    Generate one adversarial image and save it as PNG.
    Returns the saved file path.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Could not read image: {image_path}")

    print(f"[*] Loading YOLOv8 model ({YOLO_MODEL})…")
    yolo, torch_model = load_model()

    print(f"[*] Preprocessing {Path(image_path).name} "
          f"({img_bgr.shape[1]}×{img_bgr.shape[0]}) → letterbox 640×640…")
    img_tensor, _ = preprocess(img_bgr)

    print(f"[*] Running FGSM (ε={epsilon:.4f} = {epsilon*255:.1f}/255)…")
    img_adv_tensor, clean_conf, adv_conf = fgsm_attack(torch_model, img_tensor, epsilon)

    drop = clean_conf - adv_conf
    print(f"    Clean confidence     : {clean_conf:.4f}")
    print(f"    Adversarial confidence: {adv_conf:.4f}")
    print(f"    Confidence suppressed : {drop:.4f} ({drop / max(clean_conf, 1e-6):.1%})")

    eps_str = f"{epsilon:.4f}".replace(".", "_")
    out_dir = Path(output_dir) if output_dir else Path(image_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"adversarial_{eps_str}.png"
    cv2.imwrite(str(out_path), tensor_to_bgr(img_adv_tensor))
    print(f"[+] Adversarial image saved → {out_path}")
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(
        description="FGSM adversarial image generation against YOLOv8m"
    )
    parser.add_argument(
        "--image", required=True,
        help="Path to source image containing a visible person",
    )
    parser.add_argument(
        "--epsilon", type=float, default=8 / 255,
        help="Perturbation magnitude in [0,1] (default: 8/255 ≈ 0.0314)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory to save the adversarial image (default: same as input)",
    )
    args = parser.parse_args()
    run(args.image, args.epsilon, args.output_dir)


if __name__ == "__main__":
    main()
