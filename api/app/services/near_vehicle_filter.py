from app.models.detection import VehicleDetection


class NearVehicleFilter:
    def apply(
        self,
        detections: list[VehicleDetection],
        min_area_percent: float,
        min_bottom_position: float,
        max_detections: int,
    ) -> tuple[list[VehicleDetection], int]:
        nearby = [
            detection
            for detection in detections
            if detection.area_percent >= min_area_percent
            and detection.bottom_position >= min_bottom_position
        ]
        nearby.sort(key=lambda detection: detection.near_score, reverse=True)
        selected = nearby[:max_detections]
        return selected, len(detections) - len(selected)
