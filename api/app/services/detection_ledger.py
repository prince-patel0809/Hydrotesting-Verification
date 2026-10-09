from datetime import datetime, timezone
from threading import Lock

from app.models.detection import VehicleDetection, VehicleLogRecord, VehicleLogSummary


class DetectionLedger:
    def __init__(self, max_records: int = 200) -> None:
        self.max_records = max_records
        self._records: dict[str, VehicleLogRecord] = {}
        self._lock = Lock()

    def observe_frame(
        self,
        detections: list[VehicleDetection],
        frame_number: int,
        annotated_image: str,
    ) -> tuple[list[VehicleLogSummary], list[VehicleLogRecord], dict[str, int]]:
        now = datetime.now(timezone.utc)
        updates: list[VehicleLogRecord] = []
        with self._lock:
            for detection in detections:
                vehicle_id = detection.vehicle_id
                existing = self._records.get(vehicle_id)
                identified = detection.plate.india_format_valid
                registration = (
                    detection.plate.normalized_text if identified else None
                )
                if existing is None:
                    record = VehicleLogRecord(
                        vehicle_id=vehicle_id,
                        vehicle_type=detection.vehicle_type,
                        confidence=detection.confidence,
                        registration=registration,
                        identified=identified,
                        plate_status=detection.plate.status,
                        first_seen=now,
                        last_seen=now,
                        frames_seen=1,
                        best_frame_number=frame_number,
                        sharpness_score=detection.sharpness_score,
                        detection=detection,
                        best_frame_image=annotated_image,
                    )
                    self._records[vehicle_id] = record
                    updates.append(record)
                    continue

                sharper = detection.sharpness_score > existing.sharpness_score
                has_valid_plate = identified or existing.identified
                best_registration = registration if identified else existing.registration
                best_plate_status = detection.plate.status if (identified or not existing.identified) else existing.plate_status
                record = existing.model_copy(
                    update={
                        "confidence": max(detection.confidence, existing.confidence),
                        "registration": best_registration,
                        "identified": has_valid_plate,
                        "plate_status": best_plate_status,
                        "last_seen": now,
                        "frames_seen": existing.frames_seen + 1,
                        "best_frame_number": (
                            frame_number if sharper else existing.best_frame_number
                        ),
                        "sharpness_score": (
                            detection.sharpness_score
                            if sharper
                            else existing.sharpness_score
                        ),
                        "detection": detection if sharper else existing.detection,
                        "best_frame_image": (
                            annotated_image if sharper else existing.best_frame_image
                        ),
                    }
                )
                self._records[vehicle_id] = record
                if sharper:
                    updates.append(record)

            while len(self._records) > self.max_records:
                oldest_id = min(
                    self._records,
                    key=lambda vehicle_id: self._records[vehicle_id].last_seen,
                )
                del self._records[oldest_id]

            records = sorted(
                self._records.values(),
                key=lambda record: record.last_seen,
                reverse=True,
            )
            summaries = [
                VehicleLogSummary.model_validate(
                    record.model_dump(exclude={"best_frame_image"})
                )
                for record in records
            ]
            counts = {
                "identified": sum(record.identified for record in records),
                "needs_review": sum(not record.identified for record in records),
                "total": len(records),
            }
            return summaries, updates, counts
