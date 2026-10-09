from __future__ import annotations

import base64
from math import ceil
import os
from pathlib import Path
import re
from typing import Literal

import cv2
import numpy as np
import pytesseract
from numpy.typing import NDArray
from pytesseract import TesseractNotFoundError

from app.models.detection import BoundingBox, PlateRecognition, VehicleDetection

# Auto-discover Tesseract binary on Windows
DEFAULT_TESSERACT_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    Path(os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")),
    Path(os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe")),
]
tess_cmd = os.getenv("TESSERACT_CMD")
if not tess_cmd:
    for p in DEFAULT_TESSERACT_PATHS:
        if p.exists():
            tess_cmd = str(p)
            break
if tess_cmd:
    pytesseract.pytesseract.tesseract_cmd = tess_cmd

INDIAN_STATE_CODES = frozenset({
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HP", "HR",
    "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "PB",
    "PY", "RJ", "SK", "TN", "TR", "TS", "UK", "UP", "WB", "BH"
})

INDIAN_REGISTRATION = re.compile(
    r"^(?:[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{1,4}|BH\d{2}[A-Z]{2}\d{4})$"
)
INDIAN_REGISTRATION_SEARCH = re.compile(
    r"BH\d{2}[A-Z]{2}\d{4}|[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{1,4}"
)
BH_REGISTRATION = re.compile(r"^BH\d{2}[A-Z]{2}\d{4}$")
FANCY_SUFFIXES = frozenset({"0001", "0007", "0009", "0786", "1111", "7777", "9999"})
PREPROCESSING_STEPS = [
    "vehicle crop",
    "grayscale",
    "CLAHE contrast enhancement",
    "bilateral denoising",
    "adaptive threshold",
    "4x upscale",
]


def normalize_registration(text: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    if cleaned.startswith("IND") and len(cleaned) > 7:
        cleaned = cleaned[3:]
    elif cleaned.startswith("INDIA") and len(cleaned) > 9:
        cleaned = cleaned[5:]
    return cleaned


def repair_indian_plate_ocr(text: str) -> str:
    """Fix common optical character recognition errors on Indian license plates."""
    text = normalize_registration(text)
    if len(text) < 7 or len(text) > 11:
        return text

    chars = list(text)
    # 1. State code (First 2 chars must be alphabetic)
    for i in range(min(2, len(chars))):
        if chars[i] == '0': chars[i] = 'O'
        elif chars[i] == '1': chars[i] = 'I'
        elif chars[i] == '8': chars[i] = 'B'
        elif chars[i] == '5': chars[i] = 'S'
        elif chars[i] == '2': chars[i] = 'Z'

    state = "".join(chars[:2])
    if state in INDIAN_STATE_CODES or state == "BH":
        # 2. RTO digits (chars 2..3 or 2..4 should be numeric)
        idx = 2
        while idx < min(4, len(chars)) and (chars[idx].isdigit() or chars[idx] in "OIZSB"):
            if chars[idx] == 'O': chars[idx] = '0'
            elif chars[idx] == 'I': chars[idx] = '1'
            elif chars[idx] == 'Z': chars[idx] = '2'
            elif chars[idx] == 'S': chars[idx] = '5'
            elif chars[idx] == 'B': chars[idx] = '8'
            idx += 1

        # 3. Last 4 characters should be numeric
        tail_start = max(idx, len(chars) - 4)
        for j in range(tail_start, len(chars)):
            if chars[j] == 'O': chars[j] = '0'
            elif chars[j] == 'I': chars[j] = '1'
            elif chars[j] == 'Z': chars[j] = '2'
            elif chars[j] == 'S': chars[j] = '5'
            elif chars[j] == 'B': chars[j] = '8'

        return "".join(chars)

    return text


def extract_registration(text: str) -> str | None:
    raw_norm = normalize_registration(text)
    repaired = repair_indian_plate_ocr(raw_norm)

    # 1. Direct repaired full match
    if len(repaired) >= 7 and INDIAN_REGISTRATION.fullmatch(repaired):
        return repaired

    # 2. Substring matches
    for match in INDIAN_REGISTRATION_SEARCH.finditer(repaired):
        candidate = match.group()
        if len(candidate) >= 7 and INDIAN_REGISTRATION.fullmatch(candidate):
            return candidate

    for match in INDIAN_REGISTRATION_SEARCH.finditer(raw_norm):
        candidate = match.group()
        if len(candidate) >= 7 and INDIAN_REGISTRATION.fullmatch(candidate):
            return candidate

    return None


def classify_registration(text: str) -> tuple[bool, str | None, bool]:
    valid = bool(INDIAN_REGISTRATION.fullmatch(text))
    if not valid:
        return False, None, False

    category = "Bharat series" if BH_REGISTRATION.fullmatch(text) else "Indian state/UT"
    suffix = re.search(r"(\d{1,4})$", text)
    special = bool(
        suffix
        and (
            suffix.group(1).zfill(4) in FANCY_SUFFIXES
            or len(set(suffix.group(1))) == 1
        )
    )
    return True, category, special


class PlateOCR:
    def recognize(
        self,
        image: NDArray[np.uint8],
        vehicle: VehicleDetection,
        enabled: bool,
    ) -> PlateRecognition:
        if not enabled:
            return PlateRecognition(status="disabled", candidate_found=False)

        height, width = image.shape[:2]
        x1 = max(0, int(vehicle.box.x1))
        y1 = max(0, int(vehicle.box.y1))
        x2 = min(width, ceil(vehicle.box.x2))
        y2 = min(height, ceil(vehicle.box.y2))
        vehicle_crop = image[y1:y2, x1:x2]

        candidate = self._find_plate_candidate(vehicle_crop)
        raw_text: str | None = None
        plate_crop: NDArray[np.uint8] | None = None
        plate_coordinates: tuple[int, int, int, int] | None = None
        localization_method: Literal["contour", "lower_center_fallback"] | None = None

        if candidate is not None:
            plate_crop, plate_coordinates = candidate
            localization_method = "contour"
            try:
                raw_text = self._read_plate_text(self._enhance(plate_crop))
            except TesseractNotFoundError:
                return self._unavailable(
                    candidate,
                    "Tesseract is not installed or is not available on PATH.",
                    (x1, y1),
                )

        normalized = extract_registration(raw_text or "")
        if normalized is None:
            fallback = self._estimate_plate_region(vehicle_crop)
            if fallback is not None:
                fallback_crop, fallback_box = fallback
                try:
                    fallback_text = self._read_plate_text(self._enhance(fallback_crop))
                except TesseractNotFoundError:
                    if candidate is None:
                        return PlateRecognition(
                            status="unavailable",
                            candidate_found=False,
                            message="Tesseract is not installed or is not available on PATH.",
                        )
                else:
                    fallback_registration = extract_registration(fallback_text)
                    if fallback_registration is not None or (not raw_text and fallback_text):
                        raw_text = fallback_text or raw_text
                        normalized = fallback_registration
                        plate_crop = fallback_crop
                        plate_coordinates = fallback_box
                        localization_method = "lower_center_fallback"

        if candidate is None and normalized is None:
            fallback = self._estimate_plate_region(vehicle_crop)
            if fallback is not None:
                plate_crop, plate_coordinates = fallback
                localization_method = "lower_center_fallback"
            else:
                return PlateRecognition(
                    status="no_candidate",
                    candidate_found=False,
                    message="No plate-shaped region found inside this vehicle crop.",
                )

        if plate_crop is None or plate_coordinates is None:
            raise RuntimeError("Plate candidate coordinates are missing.")

        enhanced = self._enhance(plate_crop)
        encoded, buffer = cv2.imencode(".jpg", enhanced)
        enhanced_crop = (
            f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('ascii')}"
            if encoded
            else None
        )
        plate_x1, plate_y1, plate_x2, plate_y2 = plate_coordinates
        plate_box = BoundingBox(
            x1=x1 + plate_x1,
            y1=y1 + plate_y1,
            x2=x1 + plate_x2,
            y2=y1 + plate_y2,
        )
        if normalized is None:
            normalized = normalize_registration(raw_text or "")
        valid, category, special = classify_registration(normalized)
        return PlateRecognition(
            status="recognized" if valid else "unreadable",
            candidate_found=candidate is not None or valid or localization_method is not None,
            box=plate_box,
            localization_method=localization_method,
            raw_text=raw_text or None,
            normalized_text=normalized or None,
            india_format_valid=valid,
            plate_category=category,
            special_number=special,
            enhanced_crop=enhanced_crop,
            preprocessing=PREPROCESSING_STEPS,
            message=None if valid else "OCR text did not match a supported Indian registration format.",
        )

    def _unavailable(
        self,
        candidate: tuple[NDArray[np.uint8], tuple[int, int, int, int]],
        message: str,
        origin: tuple[int, int],
    ) -> PlateRecognition:
        plate_crop, (crop_x1, crop_y1, crop_x2, crop_y2) = candidate
        origin_x, origin_y = origin
        encoded, buffer = cv2.imencode(".jpg", self._enhance(plate_crop))
        enhanced_crop = (
            f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('ascii')}"
            if encoded
            else None
        )
        return PlateRecognition(
            status="unavailable",
            candidate_found=True,
            box=BoundingBox(
                x1=origin_x + crop_x1,
                y1=origin_y + crop_y1,
                x2=origin_x + crop_x2,
                y2=origin_y + crop_y2,
            ),
            localization_method="contour",
            enhanced_crop=enhanced_crop,
            preprocessing=PREPROCESSING_STEPS,
            message=message,
        )

    @staticmethod
    def _estimate_plate_region(
        vehicle_crop: NDArray[np.uint8],
    ) -> tuple[NDArray[np.uint8], tuple[int, int, int, int]] | None:
        height, width = vehicle_crop.shape[:2]
        x1, x2 = int(width * 0.28), int(width * 0.84)
        y1, y2 = int(height * 0.65), int(height * 0.95)
        if x2 - x1 < 24 or y2 - y1 < 8:
            return None
        return vehicle_crop[y1:y2, x1:x2], (x1, y1, x2, y2)

    @staticmethod
    def _estimate_plate_box(
        vehicle_crop: NDArray[np.uint8],
    ) -> tuple[int, int, int, int]:
        height, width = vehicle_crop.shape[:2]
        return (
            int(width * 0.35),
            int(height * 0.70),
            int(width * 0.80),
            int(height * 0.92),
        )

    def _find_plate_candidate(
        self,
        vehicle_crop: NDArray[np.uint8],
    ) -> tuple[NDArray[np.uint8], tuple[int, int, int, int]] | None:
        height, width = vehicle_crop.shape[:2]
        if height < 8 or width < 16:
            return None

        lower_start = int(height * 0.45)
        search = vehicle_crop[lower_start:, :]
        gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        edges = cv2.Canny(gray, 45, 140)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(
            closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )

        candidates: list[tuple[float, tuple[int, int, int, int]]] = []
        for contour in contours:
            px, py, candidate_width, candidate_height = cv2.boundingRect(contour)
            aspect_ratio = candidate_width / max(candidate_height, 1)
            if (
                not 2.0 <= aspect_ratio <= 6.5
                or candidate_width < max(18, int(width * 0.08))
                or candidate_height < 7
                or candidate_width > width * 0.55
                or candidate_height > height * 0.2
                or py + candidate_height + lower_start > height * 0.95
            ):
                continue
            box_area = candidate_width * candidate_height
            score = (
                box_area
                * min(candidate_width / max(candidate_height, 1) / 4.0, 1.0)
                * (0.5 + (py + candidate_height) / max(search.shape[0], 1) * 0.5)
            )
            candidates.append(
                (
                    score,
                    (
                        px,
                        py + lower_start,
                        px + candidate_width,
                        py + lower_start + candidate_height,
                    ),
                )
            )

        if not candidates:
            return None

        _, (px1, py1, px2, py2) = max(candidates, key=lambda item: item[0])
        padding_x_left = max(3, int(width * 0.25))
        padding_x_right = max(3, int(width * 0.05))
        padding_y = max(3, int(height * 0.06))
        px1 = max(0, px1 - padding_x_left)
        py1 = max(0, py1 - padding_y)
        px2 = min(width, px2 + padding_x_right)
        py2 = min(height, py2 + padding_y)
        return vehicle_crop[py1:py2, px1:px2], (px1, py1, px2, py2)

    @staticmethod
    def _read_plate_text(enhanced: NDArray[np.uint8]) -> str:
        whitelist = (
            "--psm {mode} "
            "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
        thresholded = cv2.threshold(
            enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]
        thresholded_inv = cv2.bitwise_not(thresholded)

        candidates = [
            pytesseract.image_to_string(
                variant,
                config=whitelist.format(mode=mode),
            ).strip()
            for variant in (enhanced, thresholded, thresholded_inv)
            for mode in (7, 8, 6, 11, 13)
        ]
        valid_candidates = [
            repair_indian_plate_ocr(text)
            for text in candidates
            if classify_registration(repair_indian_plate_ocr(text))[0]
        ]
        if valid_candidates:
            return max(valid_candidates, key=len)
        return max(candidates, key=lambda text: len(normalize_registration(text)))

    @staticmethod
    def _enhance(plate_crop: NDArray[np.uint8]) -> NDArray[np.uint8]:
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
        gray = cv2.bilateralFilter(gray, 7, 45, 45)
        gray = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            15,
            7,
        )
        return cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
