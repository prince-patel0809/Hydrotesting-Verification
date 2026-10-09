import cv2
import numpy as np
from numpy.typing import NDArray

from app.models.detection import VehicleDetection


class ImageAnnotator:
    def annotate(
        self,
        image: NDArray[np.uint8],
        detections: list[VehicleDetection],
    ) -> NDArray[np.uint8]:
        annotated = image.copy()
        for detection in detections:
            box = detection.box
            top_left = (int(box.x1), int(box.y1))
            bottom_right = (int(box.x2), int(box.y2))
            color = (58, 220, 139)
            label = f"{detection.vehicle_type} {detection.confidence:.0%}"
            cv2.rectangle(annotated, top_left, bottom_right, color, 3)
            self._draw_label(annotated, label, top_left, color)

            if detection.plate.box is not None:
                plate = detection.plate.box
                plate_top_left = (int(plate.x1), int(plate.y1))
                plate_bottom_right = (int(plate.x2), int(plate.y2))
                plate_color = (28, 183, 255)
                cv2.rectangle(
                    annotated, plate_top_left, plate_bottom_right, plate_color, 2
                )
                if detection.plate.normalized_text:
                    self._draw_label(
                        annotated,
                        detection.plate.normalized_text,
                        plate_top_left,
                        plate_color,
                    )
        return annotated

    @staticmethod
    def _draw_label(
        image: NDArray[np.uint8],
        label: str,
        top_left: tuple[int, int],
        color: tuple[int, int, int],
    ) -> None:
        text_y = max(top_left[1] - 10, 24)
        text_size, baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2
        )
        label_top = max(text_y - text_size[1] - baseline - 6, 0)
        cv2.rectangle(
            image,
            (top_left[0], label_top),
            (top_left[0] + text_size[0] + 12, text_y + 4),
            color,
            cv2.FILLED,
        )
        cv2.putText(
            image,
            label,
            (top_left[0] + 6, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (16, 28, 25),
            2,
            cv2.LINE_AA,
        )
