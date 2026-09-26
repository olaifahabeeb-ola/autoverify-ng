"""
utils/ocr.py — PHASE 2: REAL PLATE OCR

Replaces the Phase 1 random placeholder with an actual OCR pipeline:

    1. Decode the incoming image (base64 dataURL from the camera, raw bytes,
       or a file path).
    2. Locate the plate region using classic CV (grayscale -> bilateral
       filter -> Canny edges -> contour search for a plate-shaped rectangle).
       If no plate-shaped contour is found, we fall back to running OCR on
       the whole frame.
    3. Preprocess the crop (grayscale, Otsu threshold) for cleaner OCR.
    4. Run Tesseract OCR restricted to the character set used on Nigerian
       plates (A-Z, 0-9, and the '-' separator).
    5. Normalise the raw OCR text into the standard Nigerian plate format:
       AAA-999-AA  (3 letters, 3 digits, 2 letters), e.g. ABC-123-XY,
       FKJ-456-AB.

Requires: opencv-python-headless, pytesseract, numpy, and the system
`tesseract-ocr` binary (install with `sudo apt-get install tesseract-ocr`
on Linux, `brew install tesseract` on macOS, or the Windows installer at
https://github.com/UB-Mannheim/tesseract/wiki for Windows).

If Tesseract is not installed / not found on PATH, this module logs a
clear warning and falls back to the Phase-1 style placeholder so the rest
of the app keeps working during setup.
"""

import base64
import logging
import re
import shutil

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("autoverify.ocr")

try:
    import pytesseract
    _TESSERACT_OK = shutil.which("tesseract") is not None
    if not _TESSERACT_OK:
        logger.warning("Tesseract binary not found on PATH — OCR will use fallback mode.")
except ImportError:
    _TESSERACT_OK = False
    logger.warning("pytesseract not installed — OCR will use fallback mode.")

# Nigerian plate format: 3 letters - 3 digits - 2 letters (e.g. ABC-123-XY)
_PLATE_REGEX = re.compile(r"([A-Z]{3})[\s\-]*?(\d{3})[\s\-]*?([A-Z]{2})")

_OCR_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"

_DEMO_FALLBACK_PLATES = ["ABC-123-XY", "LND-456-KJ", "KAN-789-QW", "ABJ-321-ZZ"]


# --------------------------------------------------------------------------
# Image decoding
# --------------------------------------------------------------------------

def _decode_image(image_source):
    """
    Accepts:
      - a base64 data URL string (e.g. "data:image/png;base64,....")
      - raw bytes
      - a file path string
    Returns a BGR numpy array (OpenCV image) or None if decoding fails.
    """
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
            # treat as a file path
            return cv2.imread(image_source, cv2.IMREAD_COLOR)

    except Exception as exc:
        logger.warning("Could not decode image for OCR: %s", exc)
        return None

    return None


# --------------------------------------------------------------------------
# Plate region localisation
# --------------------------------------------------------------------------

def _locate_plate_candidates(gray):
    """
    Classic-CV plate localisation: blur -> edges -> contours -> filter by
    plate-like aspect ratio. Returns a list of (x, y, w, h) boxes, largest
    area first. Empty list if nothing plausible is found.
    """
    blur = cv2.bilateralFilter(gray, 11, 17, 17)
    edges = cv2.Canny(blur, 30, 200)

    contours, _ = cv2.findContours(edges.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:20]

    candidates = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if h == 0:
            continue
        aspect_ratio = w / float(h)
        # Nigerian plates are wide rectangles roughly 2:1 to 6:1
        if 2.0 <= aspect_ratio <= 6.0 and w > 60 and h > 12:
            candidates.append((x, y, w, h))

    return candidates


def _preprocess_for_ocr(crop_gray):
    """Otsu threshold + slight upscaling for small crops -> cleaner OCR."""
    h, w = crop_gray.shape[:2]
    if h < 60:
        scale = 60.0 / h
        crop_gray = cv2.resize(crop_gray, (int(w * scale), int(h * scale)),
                                interpolation=cv2.INTER_CUBIC)

    crop_gray = cv2.GaussianBlur(crop_gray, (3, 3), 0)
    _, thresh = cv2.threshold(crop_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def _run_tesseract(image):
    config = f"--psm 7 -c tessedit_char_whitelist={_OCR_WHITELIST}"
    return pytesseract.image_to_string(image, config=config)


def _normalise_plate(raw_text):
    """
    Try to coerce noisy OCR output into the standard Nigerian plate format
    AAA-999-AA. Returns the normalised string, or None if no plausible
    plate pattern is found.
    """
    cleaned = raw_text.upper()
    cleaned = re.sub(r"[^A-Z0-9]", "", cleaned)

    match = _PLATE_REGEX.search(cleaned)
    # regex above expects separators; run it against the raw (non-stripped)
    # text too, since it tolerates spaces/dashes
    if not match:
        match = _PLATE_REGEX.search(raw_text.upper())

    if match:
        letters1, digits, letters2 = match.groups()
        return f"{letters1}-{digits}-{letters2}"

    return None


def _render_character_templates():
    """Create simple letter/digit templates for fallback OCR when Tesseract is unavailable."""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    templates = {}
    for ch in chars:
        image = Image.new("L", (40, 40), 255)
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
        draw.text((6, 4), ch, fill=0, font=font)
        arr = np.array(image)
        _, thresh = cv2.threshold(arr, 200, 255, cv2.THRESH_BINARY)
        templates[ch] = thresh
    return templates


_TEMPLATE_CHARS = _render_character_templates()


def _fallback_plate_from_crop(gray_crop):
    """Best-effort OCR fallback using contour segmentation and template matching."""
    if gray_crop is None or gray_crop.size == 0:
        return None

    _, binary = cv2.threshold(gray_crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    pieces = []
    crop_h, crop_w = gray_crop.shape[:2]
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        if area < 25 or w < 6 or h < 10:
            continue
        if w > crop_w * 0.8 and h > crop_h * 0.8:
            continue
        if w * h > crop_w * crop_h * 0.6:
            continue
        aspect = w / max(h, 1)
        if not (0.2 <= aspect <= 2.0):
            continue
        pieces.append((x, y, w, h))

    if not pieces:
        return None

    pieces = sorted(pieces, key=lambda p: p[0])
    chars = []
    for x, y, w, h in pieces:
        crop = gray_crop[y:y + h, x:x + w]
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA)
        _, crop = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        best_char = None
        best_score = None
        for candidate, template in _TEMPLATE_CHARS.items():
            template = cv2.resize(template, (32, 32), interpolation=cv2.INTER_AREA)
            diff = np.mean(np.abs(crop.astype(np.int16) - template.astype(np.int16)))
            if best_score is None or diff < best_score:
                best_score = diff
                best_char = candidate
        if best_char:
            chars.append(best_char)

    if not chars:
        return None

    text = "".join(chars)
    text = re.sub(r"[^A-Z0-9]", "", text.upper())
    if len(text) == 8 and re.fullmatch(r"[A-Z]{3}[0-9]{3}[A-Z]{2}", text):
        return f"{text[:3]}-{text[3:6]}-{text[6:]}"
    if len(text) >= 8:
        candidate = text[:8]
        if re.fullmatch(r"[A-Z0-9]{8}", candidate):
            chars1 = candidate[:3]
            chars2 = candidate[3:6]
            chars3 = candidate[6:8]
            if chars1.isalpha() and chars2.isdigit() and chars3.isalpha():
                return f"{chars1}-{chars2}-{chars3}"
    return None


def _fallback_read_plate_from_image(img):
    """Fallback OCR on full images / plate candidates when Tesseract is unavailable."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    candidates = _locate_plate_candidates(gray)
    for x, y, w, h in candidates:
        crop = gray[y:y + h, x:x + w]
        plate = _fallback_plate_from_crop(crop)
        if plate:
            return plate

    fallback = _fallback_plate_from_crop(gray)
    if fallback:
        return fallback

    logger.info("No confident plate match found by fallback OCR — no plate was read from this image.")
    return None


# --------------------------------------------------------------------------
# Public API (same signature as Phase 1 placeholder)
# --------------------------------------------------------------------------

def read_plate(image_source=None):
    """
    Real OCR entry point.

    Args:
        image_source: base64 data URL string, raw image bytes, or file path.

    Returns:
        str: best-guess plate number in AAA-999-AA format. If OCR fails to
        find a confident match (e.g. blurry photo, tesseract missing), a
        random plate from the demo fallback list is returned so the rest
        of the workflow keeps functioning end-to-end during development
        and demos.
    """
    img = _decode_image(image_source)
    if img is None:
        logger.warning("No usable image for OCR — no plate was read.")
        return None

    if not _TESSERACT_OK:
        logger.warning("Tesseract unavailable — using local OCR fallback path.")
        return _fallback_read_plate_from_image(img)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    candidates = _locate_plate_candidates(gray)

    # 1) Try OCR on each plate-shaped candidate region, largest first
    for (x, y, w, h) in candidates:
        crop = gray[y:y + h, x:x + w]
        processed = _preprocess_for_ocr(crop)
        try:
            text = _run_tesseract(processed)
        except Exception as exc:
            logger.warning("Tesseract error on candidate region: %s", exc)
            continue

        plate = _normalise_plate(text)
        if plate:
            return plate

    # 2) Fall back to OCR on the whole frame
    try:
        whole_processed = _preprocess_for_ocr(gray)
        text = _run_tesseract(whole_processed)
        plate = _normalise_plate(text)
        if plate:
            return plate
    except Exception as exc:
        logger.warning("Tesseract error on full frame: %s", exc)

    # 3) Nothing confident found — do not invent a plate number.
    logger.info("No confident plate match found by OCR — no plate was read from the image.")
    return None


def is_ocr_available():
    """PHASE 3: used by the /health page to report whether real OCR (vs.
    fallback placeholder mode) is active."""
    return _TESSERACT_OK


def locate_and_read_plates(image_source=None, max_results=10):
    """
    PHASE 3: MULTI-VEHICLE DETECTION

    Scans an image (e.g. a checkpoint photo containing several cars) for
    ALL plate-shaped regions, not just the single best one, and runs OCR
    on each independently. This is a simplified "region proposal" approach
    using classic CV rather than a full object-detection model: any
    contour with a plate-like aspect ratio is treated as a candidate
    vehicle plate.

    Args:
        image_source: base64 data URL string, raw image bytes, or file path.
        max_results: cap on how many distinct plates to return.

    Returns:
        list[dict]: each item is
            {"plate_number": str, "bbox": (x, y, w, h)}
        `bbox` is the plate's own bounding box in the ORIGINAL image, which
        callers (see utils/recognition.py) expand outward to approximate
        the surrounding vehicle body for colour/make/model recognition.

        If no plate-shaped contours are found at all (e.g. a single close-up
        photo of one plate, or a low-quality frame), this falls back to the
        same single-plate behaviour as read_plate(), returning a one-item
        list covering the whole frame — so single-vehicle scans keep working
        exactly as they did in Phase 2.
    """
    img = _decode_image(image_source)
    if img is None:
        logger.warning("No usable image for multi-plate OCR — no plate was read.")
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_h, img_w = gray.shape[:2]

    if not _TESSERACT_OK:
        logger.warning("Tesseract unavailable — using local OCR fallback path for multi-scan.")
        fallback_plate = _fallback_read_plate_from_image(img)
        if not fallback_plate:
            return []
        return [{"plate_number": fallback_plate, "bbox": (0, 0, img_w, img_h)}]

    candidates = _locate_plate_candidates(gray)

    results = []
    seen_plates = set()

    for (x, y, w, h) in candidates:
        if len(results) >= max_results:
            break
        crop = gray[y:y + h, x:x + w]
        processed = _preprocess_for_ocr(crop)
        try:
            text = _run_tesseract(processed)
        except Exception as exc:
            logger.warning("Tesseract error on candidate region: %s", exc)
            continue

        plate = _normalise_plate(text)
        if plate and plate not in seen_plates:
            seen_plates.add(plate)
            results.append({"plate_number": plate, "bbox": (x, y, w, h)})

    if results:
        return results

    # No plate-shaped contours found at all — fall back to single-plate
    # behaviour. If no plate is readable, return no detections instead of
    # inventing one.
    single_plate = read_plate(image_source)
    if not single_plate:
        return []
    return [{"plate_number": single_plate, "bbox": (0, 0, img_w, img_h)}]
