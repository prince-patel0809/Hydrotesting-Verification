from threading import Lock

from app.models.detection import BoundingBox, VehicleDetection


class VehicleTracker:
    def __init__(self, match_threshold: float = 0.3, max_gap: int = 5) -> None:
        self.match_threshold = match_threshold
        self.max_gap = max_gap
        self._next_id = 1
        self._tracks: dict[str, tuple[str, BoundingBox, int]] = {}
        self._lock = Lock()

    def assign(
        self,
        detections: list[VehicleDetection],
        frame_number: int,
    ) -> list[VehicleDetection]:
        with self._lock:
            active_tracks = {
                vehicle_id: track
                for vehicle_id, track in self._tracks.items()
                if frame_number - track[2] <= self.max_gap
            }
            used_ids: set[str] = set()
            identified: list[VehicleDetection] = []

            for detection in detections:
                match_id = None
                match_iou = self.match_threshold
                for vehicle_id, (vehicle_type, box, last_frame) in active_tracks.items():
                    if (
                        vehicle_id in used_ids
                        or vehicle_type != detection.vehicle_type
                        or frame_number - last_frame > self.max_gap
                    ):
                        continue
                    overlap = self._intersection_over_union(detection.box, box)
                    if overlap > match_iou:
                        match_id, match_iou = vehicle_id, overlap

                if match_id is None:
                    match_id = f"VEH-{self._next_id:04d}"
                    self._next_id += 1

                used_ids.add(match_id)
                self._tracks[match_id] = (
                    detection.vehicle_type,
                    detection.box,
                    frame_number,
                )
                identified.append(detection.model_copy(update={"vehicle_id": match_id}))
            return identified

    @staticmethod
    def _intersection_over_union(first: BoundingBox, second: BoundingBox) -> float:
        intersection_width = max(0.0, min(first.x2, second.x2) - max(first.x1, second.x1))
        intersection_height = max(0.0, min(first.y2, second.y2) - max(first.y1, second.y1))
        intersection = intersection_width * intersection_height
        first_area = (first.x2 - first.x1) * (first.y2 - first.y1)
        second_area = (second.x2 - second.x1) * (second.y2 - second.y1)
        union = first_area + second_area - intersection
        return intersection / union if union > 0 else 0.0
