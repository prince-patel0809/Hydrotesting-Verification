from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Union

import numpy as np
from numpy.typing import NDArray

from app.core.config import MAX_CONCURRENT_PLATE_OCR
from app.models.detection import DetectionSettings, VehicleDetection
from app.services.image_annotator import ImageAnnotator
from app.services.image_source import SampleImageSource, VideoSource
from app.services.near_vehicle_filter import NearVehicleFilter
from app.services.plate_ocr import PlateOCR
from app.services.vehicle_detector import VehicleDetector
from app.services.vehicle_tracker import VehicleTracker

AnySource = Union[VideoSource, SampleImageSource]

ProgressCallback = Callable[[str, str, int], None]


@dataclass(frozen=True)
class PipelineResult:
    source_image: NDArray[np.uint8]
    annotated_image: NDArray[np.uint8]
    detections: list[VehicleDetection]
    candidates_before_filter: int
    filtered_out_count: int
    model_name: str
    settings: DetectionSettings
    frame_number: int


class VehicleDetectionPipeline:
    def __init__(
        self,
        source: AnySource,
        detector: VehicleDetector,
        annotator: ImageAnnotator,
        vehicle_filter: NearVehicleFilter,
        plate_ocr: PlateOCR,
    ) -> None:
        self.source = source
        self.detector = detector
        self.annotator = annotator
        self.vehicle_filter = vehicle_filter
        self.plate_ocr = plate_ocr

    def run(
        self,
        settings: DetectionSettings,
        progress_callback: ProgressCallback | None = None,
        frame_number: int = 1,
        vehicle_tracker: VehicleTracker | None = None,
    ) -> PipelineResult:
        def report(stage: str, detail: str, percent: int) -> None:
            if progress_callback is not None:
                progress_callback(stage, detail, percent)

        source_label = "video frame" if isinstance(self.source, VideoSource) else "camera frame"
        report("loading", f"Reading {source_label}", 5)
        source_image = self.source.read()
        report("detecting", "Detecting vehicles in frame", 15)
        candidates = self.detector.detect(
            source_image,
            settings.confidence_threshold,
        )
        report(
            "filtering",
            f"Filtering {len(candidates)} vehicle candidates by near-field settings",
            40,
        )
        nearby, filtered_out_count = self.vehicle_filter.apply(
            candidates,
            min_area_percent=settings.min_area_percent,
            min_bottom_position=settings.min_bottom_position,
            max_detections=settings.max_detections,
        )
        tracker = vehicle_tracker if vehicle_tracker is not None else VehicleTracker()
        nearby = tracker.assign(nearby, frame_number)

        def recognize(indexed_detection: tuple[int, VehicleDetection]) -> VehicleDetection:
            index, detection = indexed_detection
            report(
                "plate_ocr",
                f"Checking plate for vehicle {index} of {len(nearby)}",
                45 + int(35 * (index - 1) / max(len(nearby), 1)),
            )
            return detection.model_copy(
                update={
                    "plate": self.plate_ocr.recognize(
                        source_image,
                        detection,
                        settings.ocr_enabled,
                    )
                }
            )

        indexed_nearby = list(enumerate(nearby, start=1))
        if indexed_nearby:
            with ThreadPoolExecutor(
                max_workers=min(MAX_CONCURRENT_PLATE_OCR, len(indexed_nearby))
            ) as executor:
                detections = list(executor.map(recognize, indexed_nearby))
        else:
            detections = []
        report("annotating", "Drawing vehicle and verified-plate boxes", 85)
        annotated_image = self.annotator.annotate(source_image, detections)
        report("complete", "Frame analysis complete", 100)
        return PipelineResult(
            source_image=source_image,
            annotated_image=annotated_image,
            detections=detections,
            candidates_before_filter=len(candidates),
            filtered_out_count=filtered_out_count,
            model_name=self.detector.model_name,
            settings=settings,
            frame_number=frame_number,
        )
