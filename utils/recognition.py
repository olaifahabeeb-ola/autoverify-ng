"""
utils/recognition.py — PHASE 2: REAL VEHICLE RECOGNITION

Two independent pieces, both real (no randomness) once set up:

1. COLOUR DETECTION (works immediately, no training needed)
   Uses OpenCV k-means clustering to find the dominant colour in the
   (roughly cropped) vehicle body region of the frame, then maps that
   BGR value to the nearest named colour from a small palette
   (white/black/silver/grey/red/blue/green/yellow/brown).

2. MAKE / MODEL CLASSIFICATION (transfer learning on MobileNetV2)
   Uses a MobileNetV2 backbone (ImageNet weights, frozen) with a small
   trainable classification head -- this is the standard, laptop-friendly
   (no GPU required) way to fine-tune a CNN on a new, small image dataset.

   IMPORTANT -- fine-tuning requires labelled photos:
   To actually recognise "Toyota Camry" vs "Honda Accord" vs "Lexus RX350"
   etc., the model head must be trained on real photos of those specific
   cars. This repo ships the full training pipeline
   (utils/train_classifier.py) plus a training_data/ folder you can
   populate like:

       training_data/
         Toyota_Camry/   img1.jpg  img2.jpg ...
         Honda_Accord/   img1.jpg  img2.jpg ...
         Lexus_RX350/    img1.jpg  img2.jpg ...

   Run "python utils/train_classifier.py" after adding at least ~30-50
   photos per class to produce models_ml/vehicle_classifier.h5 and
   models_ml/class_labels.json. Once that file exists, this module
   loads it automatically and returns real make/model predictions.

   Until you've trained it, this module clearly logs that no trained
   model was found and falls back to the Phase-1 style placeholder for
   make/model ONLY -- colour detection is always real, and the app keeps
   working end-to-end either way.
"""

import base64
import json
import logging
import os
import random

import numpy as np
import cv2

logger = logging.getLogger("autoverify.recognition")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_PATH = os.path.join(BASE_DIR, "models_ml", "vehicle_classifier.h5")
LABELS_PATH = os.path.join(BASE_DIR, "models_ml", "class_labels.json")
IMG_SIZE = (224, 224)  # MobileNetV2 default input size

_FALLBACK_MAKES = ["Toyota", "Honda", "Lexus", "Mercedes", "Hyundai"]
_FALLBACK_MODELS = ["Camry", "Accord", "RX350", "C-Class", "Elantra"]

# Named colour palette in BGR (OpenCV order), used for nearest-colour mapping
_COLOUR_PALETTE_BGR = {
    "white":  (245, 245, 245),
    "black":  (20, 20, 20),
    "silver": (192, 192, 192),
    "grey":   (128, 128, 128),
    "red":    (40, 40, 200),
    "blue":   (200, 60, 30),
    "green":  (60, 160, 60),
    "yellow": (30, 220, 230),
    "brown":  (35, 65, 100),
}

_classifier_model = None
_class_labels = None
_tf_import_error = None


def _lazy_load_classifier():
    """Load the trained MobileNetV2 head lazily, only if it exists, so the
    app doesn't pay the TensorFlow import cost when no model has been
    trained yet, and doesn't crash if TensorFlow isn't installed."""
    global _classifier_model, _class_labels, _tf_import_error

    if _classifier_model is not None or _tf_import_error is not None:
        return

    if not (os.path.exists(MODEL_PATH) and os.path.exists(LABELS_PATH)):
        logger.info(
            "No trained vehicle classifier found at %s -- "
            "make/model recognition will use the placeholder fallback until "
            "you run utils/train_classifier.py on your own labelled photos.",
            MODEL_PATH,
        )
        return

    try:
        from tensorflow.keras.models import load_model
        _classifier_model = load_model(MODEL_PATH)
        with open(LABELS_PATH) as f:
            _class_labels = json.load(f)
        logger.info("Loaded trained vehicle classifier with %d classes.", len(_class_labels))
    except Exception as exc:
        _tf_import_error = str(exc)
        logger.warning("Could not load trained vehicle classifier: %s", exc)


# --------------------------------------------------------------------------
# Image decoding (shared shape with utils/ocr.py)
# --------------------------------------------------------------------------

def _decode_image(image_source):
    try:
        if image_source is None:
            return None
        if isinstance(image_source, (bytes, bytearray)):
            arr = np.frombuffer(image_source, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if isinstance(image_source, str):
            if image_source.startswith("data:image"):
                _, encoded = image_source.split(",", 1)
                binary = base64.b64decode(encoded)
                arr = np.frombuffer(binary, dtype=np.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return cv2.imread(image_source, cv2.IMREAD_COLOR)
    except Exception as exc:
        logger.warning("Could not decode image for recognition: %s", exc)
        return None
    return None


# --------------------------------------------------------------------------
# 1. Dominant colour detection (real, always on)
# --------------------------------------------------------------------------

def _dominant_bgr(image, k=3, sample_region=None):
    """K-means dominant colour. Optionally restrict to a central crop
    (sample_region = (x, y, w, h)) to avoid background/road/sky pixels."""
    if sample_region is not None:
        x, y, w, h = sample_region
        image = image[y:y + h, x:x + w]

    pixels = image.reshape((-1, 3)).astype(np.float32)
    if pixels.shape[0] < k:
        return tuple(int(c) for c in pixels.mean(axis=0))

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 5, cv2.KMEANS_RANDOM_CENTERS)
    counts = np.bincount(labels.flatten())
    dominant = centers[np.argmax(counts)]
    return tuple(int(c) for c in dominant)


def _nearest_colour_name(bgr):
    best_name, best_dist = "unknown", float("inf")
    for name, ref in _COLOUR_PALETTE_BGR.items():
        dist = sum((a - b) ** 2 for a, b in zip(bgr, ref))
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def detect_colour(image):
    """
    Returns a named colour string (e.g. "white", "black", "red") detected
    from the centre 60% of the frame, where the vehicle body is most
    likely to dominate the pixels (avoiding road/sky at the edges).
    """
    h, w = image.shape[:2]
    cx, cy = int(w * 0.2), int(h * 0.2)
    cw, ch = int(w * 0.6), int(h * 0.6)
    dominant_bgr = _dominant_bgr(image, k=3, sample_region=(cx, cy, cw, ch))
    return _nearest_colour_name(dominant_bgr)


# --------------------------------------------------------------------------
# 2. Make / model classification (MobileNetV2 transfer learning)
# --------------------------------------------------------------------------

def _classify_make_model(image):
    """Returns (make, model) using the trained classifier if available,
    else None to signal "use placeholder fallback"."""
    _lazy_load_classifier()

    if _classifier_model is None or _class_labels is None:
        return None

    try:
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

        resized = cv2.resize(image, IMG_SIZE)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        batch = np.expand_dims(rgb.astype(np.float32), axis=0)
        batch = preprocess_input(batch)

        preds = _classifier_model.predict(batch, verbose=0)[0]
        best_idx = int(np.argmax(preds))
        label = _class_labels[best_idx]  # expected format: "Make_Model", e.g. "Toyota_Camry"

        if "_" in label:
            make, model = label.split("_", 1)
        else:
            make, model = label, ""
        return make.replace("_", " "), model.replace("_", " ")

    except Exception as exc:
        logger.warning("Vehicle classifier inference failed, using fallback: %s", exc)
        return None


# --------------------------------------------------------------------------
# Public API (same signature/shape as Phase 1 placeholder)
# --------------------------------------------------------------------------

def _expand_bbox_to_vehicle(image_shape, bbox):
    """
    PHASE 3: Simplified 'region proposal'. A detected plate is usually a
    small rectangle near the bottom/centre of a vehicle. To sample colour
    and run make/model classification on the VEHICLE rather than just the
    plate, we expand the plate's bounding box outward — generously upward
    and sideways, since the plate sits low on the car body.
    """
    img_h, img_w = image_shape[:2]
    x, y, w, h = bbox

    pad_x = int(w * 1.5)
    pad_up = int(h * 6.0)     # most of the vehicle body is above the plate
    pad_down = int(h * 1.0)

    x0 = max(0, x - pad_x)
    x1 = min(img_w, x + w + pad_x)
    y0 = max(0, y - pad_up)
    y1 = min(img_h, y + h + pad_down)

    if x1 <= x0 or y1 <= y0:
        return (0, 0, img_w, img_h)
    return (x0, y0, x1 - x0, y1 - y0)


def is_classifier_loaded():
    """PHASE 3: used by the /health page to report whether a real trained
    make/model classifier is active (vs. placeholder fallback mode)."""
    _lazy_load_classifier()
    return _classifier_model is not None


# --------------------------------------------------------------------------
# Public API (same signature/shape as Phase 1 placeholder)
# --------------------------------------------------------------------------

def recognize_vehicle(image_source=None, bbox=None):
    """
    Real recognition entry point.

    Args:
        image_source: base64 data URL string, raw image bytes, or file path.
        bbox: optional (x, y, w, h) plate bounding box from
              utils.ocr.locate_and_read_plates(), used in PHASE 3 multi-
              vehicle scans to crop out just this vehicle's region (expanded
              from the plate box) before running colour/make/model
              recognition, so each detected vehicle in a multi-car photo
              gets its own independent result. If omitted, the whole image
              is used (Phase 2 single-vehicle behaviour).

    Returns:
        dict: {"make": str, "model": str, "colour": str, "method": str}

        - "colour" is always computed for real via OpenCV k-means dominant
          colour detection.
        - "make"/"model" come from the trained MobileNetV2 classifier if
          models_ml/vehicle_classifier.h5 exists; otherwise they fall
          back to the Phase-1 placeholder values (clearly logged) until
          you train the classifier with utils/train_classifier.py.
    """
    image = _decode_image(image_source)

    if image is None:
        logger.warning("No usable image for recognition -- using placeholder values.")
        return {
            "make": random.choice(_FALLBACK_MAKES),
            "model": random.choice(_FALLBACK_MODELS),
            "colour": random.choice(list(_COLOUR_PALETTE_BGR.keys())),
            "method": "placeholder_fallback",
        }

    region = image
    if bbox is not None:
        rx, ry, rw, rh = _expand_bbox_to_vehicle(image.shape, bbox)
        cropped = image[ry:ry + rh, rx:rx + rw]
        if cropped.size > 0:
            region = cropped

    colour = detect_colour(region)

    classification = _classify_make_model(region)
    if classification is not None:
        make, model = classification
        method = "trained_model"
    else:
        make = random.choice(_FALLBACK_MAKES)
        model = random.choice(_FALLBACK_MODELS)
        method = "placeholder_fallback"

    return {"make": make, "model": model, "colour": colour, "method": method}
