import asyncio
import base64
import hashlib
import logging
from asyncio import Queue
from typing import Any

import cv2
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import ValidationError

from app.core.config import DEFAULT_CONFIDENCE_THRESHOLD, FRAME_DISPATCH_INTERVAL
from app.db import Database
from app.models.detection import (
    DetectionResponse,
    DetectionSettings,
    VehicleDetection,
    VehicleLogRecord,
    VehicleLogSummary,
)
from app.pipeline import PipelineResult, VehicleDetectionPipeline
from app.services.detection_ledger import DetectionLedger
from app.services.hydrotest_verification import verify_registered_plate
from app.services.image_source import VideoSource
from app.services.vehicle_tracker import VehicleTracker

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _detection_settings(
    confidence: float,
    min_area_percent: float,
    min_bottom_position: float,
    max_detections: int,
    ocr_enabled: bool,
) -> DetectionSettings:
    return DetectionSettings(
        confidence_threshold=confidence,
        min_area_percent=min_area_percent,
        min_bottom_position=min_bottom_position,
        max_detections=max_detections,
        ocr_enabled=ocr_enabled,
    )


def _serialize_result(
    pipeline: VehicleDetectionPipeline,
    result: PipelineResult,
) -> DetectionResponse:
    encoded, image_buffer = cv2.imencode(".jpg", result.annotated_image)
    if not encoded:
        raise HTTPException(status_code=500, detail="Could not encode the annotated image.")

    height, width = result.source_image.shape[:2]
    return DetectionResponse(
        source_image=pipeline.source.filename,
        model=result.model_name,
        image_width=width,
        image_height=height,
        detection_count=len(result.detections),
        candidates_before_filter=result.candidates_before_filter,
        filtered_out_count=result.filtered_out_count,
        settings=result.settings,
        detections=result.detections,
        annotated_image=f"data:image/jpeg;base64,{base64.b64encode(image_buffer).decode('ascii')}",
    )


def _parse_settings(payload: dict[str, object]) -> DetectionSettings:
    return DetectionSettings.model_validate(
        {
            "confidence_threshold": payload.get(
                "confidence", DEFAULT_CONFIDENCE_THRESHOLD
            ),
            "min_area_percent": payload.get("min_area_percent", 1.5),
            "min_bottom_position": payload.get("min_bottom_position", 0.55),
            "max_detections": payload.get("max_detections", 5),
            "ocr_enabled": payload.get("ocr_enabled", True),
        }
    )


def _summary_payload(
    records: list[VehicleLogSummary],
    hydrotest_by_vehicle: dict[str, dict[str, Any]],
) -> list[dict[str, object]]:
    payloads = []
    for record in records:
        payload = record.model_dump(mode="json")
        payload["detection"]["plate"]["enhanced_crop"] = None
        payload["hydrotest"] = hydrotest_by_vehicle.get(record.vehicle_id)
        payloads.append(payload)
    return payloads


async def _verify_recognized_plates(
    websocket: WebSocket,
    detections: list[VehicleDetection],
    database: Database,
    hydrotest_by_vehicle: dict[str, dict[str, Any]],
    frame_number: int,
) -> None:
    pending: list[tuple[str, str]] = []
    for detection in detections:
        plate = detection.plate
        if not plate.india_format_valid or not plate.normalized_text:
            hydrotest_by_vehicle.pop(detection.vehicle_id, None)
            continue

        cached = hydrotest_by_vehicle.get(detection.vehicle_id)
        if (
            cached is not None
            and cached["plate"] == plate.normalized_text
            and cached["status"] != "UNAVAILABLE"
        ):
            continue
        pending.append((detection.vehicle_id, plate.normalized_text))

    if not pending:
        return

    await websocket.send_json(
        {
            "type": "progress",
            "frame_number": frame_number,
            "stage": "hydrotest",
            "detail": f"Checking hydrotest registry for {len(pending)} recognized plate(s)",
            "percent": 96,
        }
    )

    async def check(vehicle_id: str, plate: str) -> tuple[str, dict[str, Any]]:
        try:
            result = await asyncio.to_thread(verify_registered_plate, database, plate)
            return vehicle_id, result
        except Exception as error:
            logger.exception("Hydrotest check failed for tracked vehicle %s", vehicle_id)
            return vehicle_id, {
                "plate": plate,
                "status": "UNAVAILABLE",
                "message": "Hydrotest check failed. Manual review is required.",
                "error": str(error),
                "alert": None,
            }

    for vehicle_id, result in await asyncio.gather(
        *(check(vehicle_id, plate) for vehicle_id, plate in pending)
    ):
        hydrotest_by_vehicle[vehicle_id] = result


async def _stream_frames(
    websocket: WebSocket,
    pipeline: VehicleDetectionPipeline,
    settings: DetectionSettings,
    ledger: DetectionLedger,
    tracker: VehicleTracker,
    frame_state: list[int],
    stop_requested: asyncio.Event,
    interval_seconds: float,
    hydrotest_database: Database,
    hydrotest_by_vehicle: dict[str, dict[str, Any]],
) -> None:
    """Continuously process frames from the source and push results over WebSocket.

    For a VideoSource this reads successive video frames.  For a SampleImageSource
    the same still is processed repeatedly (demo / test mode).
    """
    last_frame_hash = ""
    loop = asyncio.get_running_loop()

    while not stop_requested.is_set():
        frame_state[0] += 1
        frame_number = frame_state[0]
        progress_events: Queue[dict[str, object]] = Queue()

        def report_progress(stage: str, detail: str, percent: int) -> None:
            loop.call_soon_threadsafe(
                progress_events.put_nowait,
                {
                    "type": "progress",
                    "frame_number": frame_number,
                    "stage": stage,
                    "detail": detail,
                    "percent": percent,
                },
            )

        worker = asyncio.create_task(
            asyncio.to_thread(
                pipeline.run,
                settings,
                report_progress,
                frame_number,
                tracker,
            )
        )
        while not worker.done():
            try:
                event = await asyncio.wait_for(progress_events.get(), timeout=0.1)
            except TimeoutError:
                continue
            await websocket.send_json(event)

        result = await worker
        while not progress_events.empty():
            await websocket.send_json(progress_events.get_nowait())
        response = _serialize_result(pipeline, result)
        annotated_hash = hashlib.sha256(
            response.annotated_image.encode("ascii")
        ).hexdigest()
        summaries, updates, counts = ledger.observe_frame(
            result.detections,
            frame_number,
            response.annotated_image,
        )
        await _verify_recognized_plates(
            websocket,
            result.detections,
            hydrotest_database,
            hydrotest_by_vehicle,
            frame_number,
        )

        def serialize_record(record: VehicleLogRecord) -> dict[str, object]:
            payload = record.model_dump(mode="json")
            payload["detection"]["plate"]["enhanced_crop"] = None
            payload["hydrotest"] = hydrotest_by_vehicle.get(record.vehicle_id)
            return payload

        await websocket.send_json(
            {
                "type": "frame",
                "frame_number": frame_number,
                "source_image": response.source_image,
                "image_width": response.image_width,
                "image_height": response.image_height,
                "annotated_image": (
                    response.annotated_image
                    if annotated_hash != last_frame_hash
                    else None
                ),
                "detection_count": response.detection_count,
                "candidates_before_filter": response.candidates_before_filter,
                "filtered_out_count": response.filtered_out_count,
                "settings": response.settings.model_dump(mode="json"),
                "detections": [
                    detection.model_dump(mode="json")
                    for detection in response.detections
                ],
                "records": _summary_payload(summaries, hydrotest_by_vehicle),
                "record_updates": [serialize_record(record) for record in updates],
                "counts": counts,
            }
        )
        last_frame_hash = annotated_hash
        try:
            await asyncio.wait_for(
                stop_requested.wait(),
                timeout=interval_seconds,
            )
        except TimeoutError:
            pass

    await websocket.send_json({"type": "status", "status": "stopped"})


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/detection", response_model=DetectionResponse)
def detect_vehicles(
    request: Request,
    confidence: float = Query(DEFAULT_CONFIDENCE_THRESHOLD, ge=0.05, le=0.95),
    min_area_percent: float = Query(1.5, ge=0.05, le=50),
    min_bottom_position: float = Query(0.55, ge=0.1, le=1),
    max_detections: int = Query(5, ge=1, le=30),
    ocr_enabled: bool = Query(True),
) -> DetectionResponse:
    pipeline: VehicleDetectionPipeline = request.app.state.detection_pipeline
    settings = _detection_settings(
        confidence,
        min_area_percent,
        min_bottom_position,
        max_detections,
        ocr_enabled,
    )
    result = pipeline.run(settings)
    return _serialize_result(pipeline, result)


@router.websocket("/detection/live")
async def live_detection(websocket: WebSocket) -> None:
    await websocket.accept()
    pipeline: VehicleDetectionPipeline = websocket.app.state.detection_pipeline
    ledger = DetectionLedger()
    stop_requested = asyncio.Event()
    tracker = VehicleTracker()
    frame_state = [0]
    replay_task: asyncio.Task[None] | None = None
    hydrotest_by_vehicle: dict[str, dict[str, Any]] = {}
    try:
        source = pipeline.source
        is_video = isinstance(source, VideoSource)
        # Send the first frame as the preview image
        first_frame = await asyncio.to_thread(source.read)
        encoded, buffer = cv2.imencode(".jpg", first_frame)
        if not encoded:
            raise RuntimeError("Could not encode the first source frame.")
        source_mode = "video-loop" if is_video else "sample-image-replay"
        default_interval = FRAME_DISPATCH_INTERVAL
        await websocket.send_json(
            {
                "type": "ready",
                "source_image": source.filename,
                "width": first_frame.shape[1],
                "height": first_frame.shape[0],
                "preview": f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('ascii')}",
                "mode": source_mode,
                "interval_seconds": default_interval,
            }
        )
        while True:
            command = await websocket.receive_json()
            if command.get("action") == "start":
                if replay_task is not None and not replay_task.done():
                    await websocket.send_json(
                        {"type": "status", "status": "running"}
                    )
                    continue
                try:
                    settings = _parse_settings(command)
                except ValidationError as error:
                    await websocket.send_json(
                        {"type": "error", "detail": str(error)}
                    )
                    continue
                interval = command.get("interval_seconds", default_interval)
                if not isinstance(interval, (int, float)) or not 0.1 <= interval <= 10:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": "interval_seconds must be between 0.5 and 10.",
                        }
                    )
                    continue
                stop_requested.clear()
                await websocket.send_json(
                    {"type": "status", "status": "running"}
                )
                replay_task = asyncio.create_task(
                    _stream_frames(
                        websocket,
                        pipeline,
                        settings,
                        ledger,
                        tracker,
                        frame_state,
                        stop_requested,
                        float(interval),
                        websocket.app.state.hydrotest_db,
                        hydrotest_by_vehicle,
                    )
                )
            elif command.get("action") == "stop":
                stop_requested.set()
                if replay_task is not None:
                    await replay_task
                    replay_task = None
            elif command.get("action") == "clear_log":
                ledger = DetectionLedger()
                hydrotest_by_vehicle.clear()
                await websocket.send_json(
                    {"type": "status", "status": "log_cleared"}
                )
            else:
                await websocket.send_json(
                    {"type": "error", "detail": "Unknown stream control action."}
                )
    except WebSocketDisconnect:
        stop_requested.set()
        if replay_task is not None:
            replay_task.cancel()
            await asyncio.gather(replay_task, return_exceptions=True)
    except Exception as error:
        stop_requested.set()
        if replay_task is not None:
            replay_task.cancel()
            await asyncio.gather(replay_task, return_exceptions=True)
        try:
            await websocket.send_json(
                {"type": "error", "detail": f"Frame processing failed: {error}"}
            )
        except RuntimeError:
            pass
