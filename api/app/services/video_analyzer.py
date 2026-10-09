"""Batch Video Analysis Service.

Processes an entire video file in one pass:
1. Samples frames at a configurable rate (e.g. 2 fps).
2. Detects vehicles using YOLO.
3. Filters near-field candidates.
4. Tracks vehicles across consecutive frames.
5. Localizes plates and executes OCR.
6. Performs CNG cylinder hydrotest verification against the database.
7. Draws annotations on each frame.
8. Retains a complete timeline of frames + tracked vehicle ledger + hydrotest compliance summary.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from app.db import Database
from app.models.detection import DetectionSettings, VehicleDetection
from app.pipeline import VehicleDetectionPipeline
from app.services.detection_ledger import DetectionLedger
from app.services.hydrotest_verification import verify_registered_plate
from app.services.vehicle_tracker import VehicleTracker

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str, int], None]  # (current_frame, total_frames, stage, percent)


@dataclass
class AnalyzedFrame:
    frame_index: int
    video_frame_number: int
    timestamp_sec: float
    image_base64: str
    detection_count: int
    detections: list[dict[str, Any]]
    active_vehicle_ids: list[str]


@dataclass
class VideoAnalysisResult:
    video_path: str
    total_video_frames: int
    fps: float
    duration_sec: float
    sampled_frames_count: int
    frames: list[AnalyzedFrame]
    vehicles: list[dict[str, Any]]
    hydrotest_summary: dict[str, Any]
    settings: dict[str, Any]


class VideoBatchAnalyzer:
    def __init__(
        self,
        pipeline: VehicleDetectionPipeline,
        database: Database,
    ) -> None:
        self.pipeline = pipeline
        self.database = database
        self._cache: dict[str, VideoAnalysisResult] = {}

    def analyze_video(
        self,
        video_path: Path,
        settings: DetectionSettings,
        *,
        sample_fps: float = 2.0,
        max_frames: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> VideoAnalysisResult:
        """Process the whole video and return timeline frames, vehicles, and hydrotest results."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FileNotFoundError(f"Could not open video file: {video_path}")

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
            duration_sec = total_frames / video_fps if total_frames > 0 else 0.0

            # Calculate frame step based on requested sample_fps
            step = max(1, int(round(video_fps / sample_fps))) if sample_fps > 0 else 30

            target_frame_indices = list(range(0, total_frames, step))
            if max_frames and len(target_frame_indices) > max_frames:
                target_frame_indices = target_frame_indices[:max_frames]

            total_to_process = len(target_frame_indices)
            frames_result: list[AnalyzedFrame] = []
            tracker = VehicleTracker()
            ledger = DetectionLedger()
            hydrotest_by_vehicle: dict[str, dict[str, Any]] = {}

            for idx, frame_no in enumerate(target_frame_indices):
                if progress_callback is not None:
                    percent = int((idx / max(1, total_to_process)) * 100)
                    progress_callback(
                        idx + 1,
                        total_to_process,
                        f"Analyzing video frame {idx + 1}/{total_to_process} ({frame_no / video_fps:.1f}s)",
                        percent,
                    )

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                ok, raw_frame = cap.read()
                if not ok or raw_frame is None:
                    continue

                timestamp_sec = round(frame_no / video_fps, 2)

                # 1. Detection
                candidates = self.pipeline.detector.detect(
                    raw_frame,
                    settings.confidence_threshold,
                )

                # 2. Near-field filtering
                nearby, _ = self.pipeline.vehicle_filter.apply(
                    candidates,
                    min_area_percent=settings.min_area_percent,
                    min_bottom_position=settings.min_bottom_position,
                    max_detections=settings.max_detections,
                )

                # 3. Tracking across frames
                tracked_detections = tracker.assign(nearby, idx + 1)

                # 4. Plate OCR & Preprocessing
                detections: list[VehicleDetection] = []
                for d in tracked_detections:
                    plate_res = self.pipeline.plate_ocr.recognize(
                        raw_frame,
                        d,
                        settings.ocr_enabled,
                    )
                    detection_with_plate = d.model_copy(update={"plate": plate_res})
                    detections.append(detection_with_plate)

                    # 5. Hydrotest verification for recognized or potential plates
                    target_plate = plate_res.normalized_text or (plate_res.raw_text if len(plate_res.raw_text or "") >= 6 else None)
                    if target_plate and d.vehicle_id not in hydrotest_by_vehicle:
                        try:
                            check_res = verify_registered_plate(self.database, target_plate)
                            hydrotest_by_vehicle[d.vehicle_id] = check_res
                        except Exception as err:
                            logger.warning("Hydrotest check failed for %s: %s", target_plate, err)
                            hydrotest_by_vehicle[d.vehicle_id] = {
                                "plate": target_plate,
                                "status": "NEEDS_REVIEW",
                                "message": f"Hydrotest lookup failed: {err}",
                                "alert": None,
                            }

                # 6. Annotation
                annotated_img = self.pipeline.annotator.annotate(raw_frame, detections)
                h, w = annotated_img.shape[:2]
                if w > 1280:
                    scale = 1280 / w
                    annotated_disp = cv2.resize(annotated_img, (1280, int(h * scale)), interpolation=cv2.INTER_AREA)
                else:
                    annotated_disp = annotated_img
                encoded, buffer = cv2.imencode(".jpg", annotated_disp, [cv2.IMWRITE_JPEG_QUALITY, 80])
                img_b64 = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('ascii')}" if encoded else ""

                # Observe in ledger for tracking sharpest frames
                summaries, updates, _ = ledger.observe_frame(detections, idx + 1, img_b64)

                detections_payload = []
                active_ids = []
                for d in detections:
                    active_ids.append(d.vehicle_id)
                    d_dict = d.model_dump(mode="json")
                    d_dict["plate"]["enhanced_crop"] = None
                    d_dict["hydrotest"] = hydrotest_by_vehicle.get(d.vehicle_id)
                    detections_payload.append(d_dict)

                frames_result.append(
                    AnalyzedFrame(
                        frame_index=idx,
                        video_frame_number=frame_no,
                        timestamp_sec=timestamp_sec,
                        image_base64=img_b64,
                        detection_count=len(detections),
                        detections=detections_payload,
                        active_vehicle_ids=active_ids,
                    )
                )

            if progress_callback is not None:
                progress_callback(total_to_process, total_to_process, "Video analysis complete", 100)

            # Re-verify and sync hydrotest records for all tracked vehicles with verified registrations
            for summary in summaries:
                reg = summary.registration
                if summary.identified and reg:
                    curr_ht = hydrotest_by_vehicle.get(summary.vehicle_id)
                    if not curr_ht or curr_ht.get("plate") != reg or curr_ht.get("status") in ("NEEDS_REVIEW", "UNAVAILABLE"):
                        try:
                            check_res = verify_registered_plate(self.database, reg)
                            hydrotest_by_vehicle[summary.vehicle_id] = check_res
                        except Exception as err:
                            logger.warning("Re-verification failed for %s: %s", reg, err)

            # Update active detection objects across all timeline frames
            for frame_obj in frames_result:
                for d_dict in frame_obj.detections:
                    vid = d_dict.get("vehicle_id")
                    if vid and vid in hydrotest_by_vehicle:
                        d_dict["hydrotest"] = hydrotest_by_vehicle[vid]

            # Build vehicle ledger list
            vehicle_list = []
            for summary in summaries:
                s_dict = summary.model_dump(mode="json")
                s_dict["detection"]["plate"]["enhanced_crop"] = None
                s_dict["hydrotest"] = hydrotest_by_vehicle.get(summary.vehicle_id)
                vehicle_list.append(s_dict)

            # Build hydrotest summary counts
            valid_count = sum(1 for v in hydrotest_by_vehicle.values() if v.get("status") == "VALID")
            expired_count = sum(1 for v in hydrotest_by_vehicle.values() if v.get("status") == "EXPIRED")
            expiring_count = sum(1 for v in hydrotest_by_vehicle.values() if v.get("status") == "EXPIRING_SOON")
            review_count = sum(1 for v in hydrotest_by_vehicle.values() if v.get("status") in ("NEEDS_REVIEW", "UNAVAILABLE"))

            db_data = self.database.dashboard_data(date.today())
            open_critical = db_data["open_alerts"].get("critical", 0)
            open_warning = db_data["open_alerts"].get("warning", 0)

            result = VideoAnalysisResult(
                video_path=str(video_path),
                total_video_frames=total_frames,
                fps=video_fps,
                duration_sec=duration_sec,
                sampled_frames_count=len(frames_result),
                frames=frames_result,
                vehicles=vehicle_list,
                hydrotest_summary={
                    "total_unique_vehicles": len(vehicle_list),
                    "vehicles_with_plates": len(hydrotest_by_vehicle),
                    "valid": valid_count,
                    "expired": expired_count,
                    "expiring_soon": expiring_count,
                    "needs_review": review_count,
                    "open_critical_alerts": open_critical,
                    "open_warning_alerts": open_warning,
                },
                settings=settings.model_dump(mode="json"),
            )

            cache_key = f"{video_path}_{settings.confidence_threshold}_{sample_fps}"
            self._cache[cache_key] = result
            return result

        finally:
            cap.release()

    def get_cached(self, video_path: Path) -> VideoAnalysisResult | None:
        for k, v in self._cache.items():
            if str(video_path) in k:
                return v
        return None
