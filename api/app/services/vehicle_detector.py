from threading import Lock

import numpy as np
import cv2
from numpy.typing import NDArray
from ultralytics import YOLO

from app.core.config import VEHICLE_CLASSES
from app.models.detection import BoundingBox, VehicleDetection


class VehicleDetector:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: YOLO | None = None
        self._lock = Lock()

    def detect(
        self,
        image: NDArray[np.uint8],
        confidence_threshold: float,
    ) -> list[VehicleDetection]:
        with self._lock:
            if self._model is None:
                self._model = YOLO(self.model_name)
            model = self._model
            result = model.predict(
                source=image,
                conf=confidence_threshold,
                classes=[
                    class_id
                    for class_id, class_name in model.names.items()
                    if class_name in VEHICLE_CLASSES
                ],
                verbose=False,
            )[0]

        if result.boxes is None:
            return []

        image_height, image_width = image.shape[:2]
        detections: list[VehicleDetection] = []
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            vehicle_crop = image[
                max(0, int(y1)) : min(image_height, int(y2)),
                max(0, int(x1)) : min(image_width, int(x2)),
            ]
            gray_crop = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
            sharpness_score = float(
                cv2.Laplacian(gray_crop, cv2.CV_64F).var()
            )
            area_percent = ((x2 - x1) * (y2 - y1)) / (image_width * image_height) * 100
            bottom_position = y2 / image_height
            near_score = 0.7 * min(area_percent / 15.0, 1.0) + 0.3 * bottom_position
            class_id = int(box.cls.item())
            detections.append(
                VehicleDetection(
                    vehicle_type=model.names[class_id],
                    confidence=float(box.conf.item()),
                    box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    area_percent=area_percent,
                    bottom_position=bottom_position,
                    near_score=near_score,
                    sharpness_score=sharpness_score,
                    plate={"status": "disabled", "candidate_found": False},
                )
            )
        return detections
