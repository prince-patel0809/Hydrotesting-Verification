import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.config import DEFAULT_CONFIDENCE_THRESHOLD, VIDEO_SOURCE_PATH
from app.models.detection import DetectionSettings
from app.services.video_analyzer import VideoAnalysisResult, VideoBatchAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video")


class VideoAnalyzeRequest(BaseModel):
    confidence: float = Field(default=DEFAULT_CONFIDENCE_THRESHOLD, ge=0.05, le=0.95)
    min_area_percent: float = Field(default=0.8, ge=0.05, le=50.0)
    min_bottom_position: float = Field(default=0.25, ge=0.05, le=1.0)
    max_detections: int = Field(default=8, ge=1, le=30)
    ocr_enabled: bool = Field(default=True)
    sample_fps: float = Field(default=1.5, ge=0.2, le=10.0)
    max_frames: int | None = Field(default=None, ge=5, le=1000)


@router.post("/analyze")
async def analyze_video(
    payload: VideoAnalyzeRequest,
    request: Request,
) -> dict[str, Any]:
    analyzer: VideoBatchAnalyzer = request.app.state.video_analyzer
    video_path = VIDEO_SOURCE_PATH
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found at {video_path}")

    settings = DetectionSettings(
        confidence_threshold=payload.confidence,
        min_area_percent=payload.min_area_percent,
        min_bottom_position=payload.min_bottom_position,
        max_detections=payload.max_detections,
        ocr_enabled=payload.ocr_enabled,
    )

    try:
        result = await asyncio.to_thread(
            analyzer.analyze_video,
            video_path,
            settings,
            sample_fps=payload.sample_fps,
            max_frames=payload.max_frames,
        )
        return _serialize_analysis_result(result)
    except Exception as err:
        logger.exception("Video batch analysis failed")
        raise HTTPException(status_code=500, detail=f"Video analysis failed: {err}")


@router.get("/analysis")
async def get_video_analysis(request: Request) -> dict[str, Any]:
    analyzer: VideoBatchAnalyzer = request.app.state.video_analyzer
    video_path = VIDEO_SOURCE_PATH
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video file not found at {video_path}")

    cached = analyzer.get_cached(video_path)
    if cached is not None:
        return _serialize_analysis_result(cached)

    # Run default analysis if not cached
    settings = DetectionSettings(
        confidence_threshold=0.20,
        min_area_percent=0.8,
        min_bottom_position=0.25,
        max_detections=8,
        ocr_enabled=True,
    )
    result = await asyncio.to_thread(
        analyzer.analyze_video,
        video_path,
        settings,
        sample_fps=1.0,
        max_frames=120,
    )
    return _serialize_analysis_result(result)


@router.websocket("/analyze/ws")
async def video_analyze_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    analyzer: VideoBatchAnalyzer = websocket.app.state.video_analyzer
    video_path = VIDEO_SOURCE_PATH

    loop = asyncio.get_running_loop()
    progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def on_progress(curr: int, total: int, stage: str, pct: int) -> None:
        loop.call_soon_threadsafe(
            progress_queue.put_nowait,
            {
                "type": "progress",
                "current_frame": curr,
                "total_frames": total,
                "stage": stage,
                "percent": pct,
            },
        )

    try:
        data = await websocket.receive_json()
        confidence = float(data.get("confidence", 0.20))
        sample_fps = float(data.get("sample_fps", 1.5))
        ocr_enabled = bool(data.get("ocr_enabled", True))
        max_frames = data.get("max_frames")
        if max_frames is not None:
            max_frames = int(max_frames)

        settings = DetectionSettings(
            confidence_threshold=confidence,
            min_area_percent=float(data.get("min_area_percent", 0.8)),
            min_bottom_position=float(data.get("min_bottom_position", 0.25)),
            max_detections=int(data.get("max_detections", 8)),
            ocr_enabled=ocr_enabled,
        )

        task = asyncio.create_task(
            asyncio.to_thread(
                analyzer.analyze_video,
                video_path,
                settings,
                sample_fps=sample_fps,
                max_frames=max_frames,
                progress_callback=on_progress,
            )
        )

        while not task.done():
            try:
                msg = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                await websocket.send_json(msg)
            except TimeoutError:
                continue

        result = await task
        while not progress_queue.empty():
            await websocket.send_json(progress_queue.get_nowait())

        await websocket.send_json(
            {
                "type": "complete",
                "result": _serialize_analysis_result(result),
            }
        )
    except WebSocketDisconnect:
        pass
    except Exception as err:
        logger.exception("WebSocket video analysis failed")
        try:
            await websocket.send_json({"type": "error", "detail": str(err)})
        except Exception:
            pass


def _serialize_analysis_result(res: VideoAnalysisResult) -> dict[str, Any]:
    return {
        "video_path": res.video_path,
        "total_video_frames": res.total_video_frames,
        "fps": res.fps,
        "duration_sec": res.duration_sec,
        "sampled_frames_count": res.sampled_frames_count,
        "frames": [
            {
                "frame_index": f.frame_index,
                "video_frame_number": f.video_frame_number,
                "timestamp_sec": f.timestamp_sec,
                "image_base64": f.image_base64,
                "detection_count": f.detection_count,
                "detections": f.detections,
                "active_vehicle_ids": f.active_vehicle_ids,
            }
            for f in res.frames
        ],
        "vehicles": res.vehicles,
        "hydrotest_summary": res.hydrotest_summary,
        "settings": res.settings,
    }
