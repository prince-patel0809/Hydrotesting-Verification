import asyncio
import base64
import hashlib
from asyncio import Queue

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

from app.core.config import DEFAULT_CONFIDENCE_THRESHOLD
from app.models.detection import (
    DetectionResponse,
    DetectionSettings,
    VehicleLogRecord,
    VehicleLogSummary,
)
from app.pipeline import PipelineResult, VehicleDetectionPipeline
from app.services.detection_ledger import DetectionLedger
from app.services.vehicle_tracker import VehicleTracker

router = APIRouter(prefix="/api")


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


def _summary_payload(records: list[VehicleLogSummary]) -> list[dict[str, object]]:
    payloads = []
    for record in records:
        payload = record.model_dump(mode="json")
        payload["detection"]["plate"]["enhanced_crop"] = None
        payloads.append(payload)
    return payloads


async def _replay_sample(
    websocket: WebSocket,
    pipeline: VehicleDetectionPipeline,
    settings: DetectionSettings,
    ledger: DetectionLedger,
    tracker: VehicleTracker,
    frame_state: list[int],
    stop_requested: asyncio.Event,
    interval_seconds: float,
) -> None:
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
                "records": _summary_payload(summaries),
                "record_updates": [
                    record.model_dump(mode="json") for record in updates
                ],
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
    try:
        source = pipeline.source.read()
        encoded, buffer = cv2.imencode(".jpg", source)
        if not encoded:
            raise RuntimeError("Could not encode the configured sample image.")
        await websocket.send_json(
            {
                "type": "ready",
                "source_image": pipeline.source.filename,
                "width": source.shape[1],
                "height": source.shape[0],
                "preview": f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('ascii')}",
                "mode": "sample-image-replay",
                "interval_seconds": 1.5,
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
                interval = command.get("interval_seconds", 1.5)
                if not isinstance(interval, (int, float)) or not 0.5 <= interval <= 10:
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
                    _replay_sample(
                        websocket,
                        pipeline,
                        settings,
                        ledger,
                        tracker,
                        frame_state,
                        stop_requested,
                        float(interval),
                    )
                )
            elif command.get("action") == "stop":
                stop_requested.set()
                if replay_task is not None:
                    await replay_task
                    replay_task = None
            elif command.get("action") == "clear_log":
                ledger = DetectionLedger()
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
