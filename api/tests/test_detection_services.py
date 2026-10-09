import unittest
from pathlib import Path

import cv2
import numpy as np

from app.models.detection import BoundingBox, PlateRecognition, VehicleDetection
from app.services.near_vehicle_filter import NearVehicleFilter
from app.services.detection_ledger import DetectionLedger
from app.services.plate_ocr import (
    PlateOCR,
    classify_registration,
    extract_registration,
    normalize_registration,
)
from app.services.vehicle_tracker import VehicleTracker


def make_detection(
    vehicle_type: str,
    area_percent: float,
    bottom_position: float,
    near_score: float,
) -> VehicleDetection:
    return VehicleDetection(
        vehicle_type=vehicle_type,
        confidence=0.9,
        box=BoundingBox(x1=10, y1=10, x2=100, y2=100),
        area_percent=area_percent,
        bottom_position=bottom_position,
        near_score=near_score,
        plate={"status": "disabled", "candidate_found": False},
    )


class NearVehicleFilterTests(unittest.TestCase):
    def test_filters_far_vehicles_sorts_nearest_and_applies_limit(self) -> None:
        detections = [
            make_detection("car", 10, 0.8, 0.8),
            make_detection("truck", 0.5, 0.9, 0.5),
            make_detection("motorcycle", 8, 0.7, 0.9),
        ]

        selected, filtered_count = NearVehicleFilter().apply(
            detections,
            min_area_percent=1,
            min_bottom_position=0.6,
            max_detections=1,
        )

        self.assertEqual([item.vehicle_type for item in selected], ["motorcycle"])
        self.assertEqual(filtered_count, 2)


class VehicleStreamTests(unittest.TestCase):
    def test_tracker_keeps_id_for_replayed_and_nearby_frames(self) -> None:
        tracker = VehicleTracker()
        first = make_detection("car", 10, 0.8, 0.8)
        moved = first.model_copy(
            update={
                "box": BoundingBox(x1=12, y1=11, x2=102, y2=101),
            }
        )

        first_id = tracker.assign([first], 1)[0].vehicle_id
        replayed_id = tracker.assign([first], 2)[0].vehicle_id
        moved_id = tracker.assign([moved], 3)[0].vehicle_id

        self.assertEqual(first_id, "VEH-0001")
        self.assertEqual(replayed_id, first_id)
        self.assertEqual(moved_id, first_id)

    def test_ledger_retains_only_the_sharpest_frame_for_a_vehicle(self) -> None:
        ledger = DetectionLedger()
        first = make_detection("car", 10, 0.8, 0.8).model_copy(
            update={
                "vehicle_id": "VEH-0001",
                "sharpness_score": 50,
                "plate": PlateRecognition(
                    status="recognized",
                    candidate_found=True,
                    normalized_text="DL3CCT8408",
                    india_format_valid=True,
                ),
            }
        )
        blurrier = first.model_copy(update={"sharpness_score": 20})
        _, first_updates, first_counts = ledger.observe_frame([first], 1, "frame-1")
        summaries, second_updates, second_counts = ledger.observe_frame(
            [blurrier], 2, "frame-2"
        )

        self.assertEqual(first_counts["identified"], 1)
        self.assertEqual(second_counts["identified"], 1)
        self.assertEqual(second_counts["total"], 1)
        self.assertEqual(len(first_updates), 1)
        self.assertEqual(second_updates, [])
        self.assertEqual(summaries[0].frames_seen, 2)
        self.assertEqual(summaries[0].best_frame_number, 1)
        self.assertEqual(summaries[0].sharpness_score, 50)


class IndianPlateTests(unittest.TestCase):
    def test_sample_vehicle_localizes_a_plate_sized_crop(self) -> None:
        image_path = Path(__file__).resolve().parents[1] / "image.jpeg"
        image = cv2.imread(str(image_path))
        vehicle_crop = image[183:402, 293:643]

        candidate = PlateOCR()._find_plate_candidate(vehicle_crop)

        self.assertIsNotNone(candidate)
        assert candidate is not None
        plate_crop, (_, y1, _, _) = candidate
        self.assertLess(plate_crop.shape[0], 70)
        self.assertLess(plate_crop.shape[1], 160)
        self.assertGreater(plate_crop.shape[1] / plate_crop.shape[0], 1.5)
        self.assertLess(y1, 160)

    def test_image_two_localizes_the_low_visibility_plate(self) -> None:
        image_path = Path(__file__).resolve().parents[1] / "image-2.png"
        image = cv2.imread(str(image_path))
        vehicle_crop = image[223:421, 91:383]

        candidate = PlateOCR()._find_plate_candidate(vehicle_crop)

        self.assertIsNotNone(candidate)
        assert candidate is not None
        plate_crop, (_, y1, _, _) = candidate
        self.assertLess(plate_crop.shape[1], 160)
        self.assertGreater(y1, 120)
        self.assertLess(y1, 170)

    def test_normalizes_state_registration_and_detects_special_suffix(self) -> None:
        normalized = normalize_registration(" tn 10 ab 0001 ")

        self.assertEqual(normalized, "TN10AB0001")
        self.assertEqual(
            classify_registration(normalized),
            (True, "Indian state/UT", True),
        )

    def test_extracts_registration_from_noisy_ocr_prefix(self) -> None:
        normalized = normalize_registration("A DL3CCT8408")

        self.assertEqual(extract_registration(normalized), "DL3CCT8408")

    def test_recognizes_bharat_series_registration(self) -> None:
        self.assertEqual(
            classify_registration("BH12AB1234"),
            (True, "Bharat series", False),
        )

    def test_preprocessing_produces_upscaled_grayscale_plate(self) -> None:
        crop = np.zeros((16, 64, 3), dtype=np.uint8)
        crop[:, 8:56] = 255

        enhanced = PlateOCR._enhance(crop)

        self.assertEqual(enhanced.shape, (64, 256))
        self.assertEqual(enhanced.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
