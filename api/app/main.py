import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import (
    FRAME_SAMPLE_INTERVAL,
    MODEL_NAME,
    SAMPLE_IMAGE_PATH,
    VIDEO_SOURCE_PATH,
)
from app.db import Database
from app.pipeline import VehicleDetectionPipeline
from app.routes.alerts import router as alerts_router
from app.routes.verify import router as verify_router
from app.routes.video_analysis import router as video_analysis_router
from app.services.image_annotator import ImageAnnotator
from app.services.image_source import SampleImageSource, VideoSource
from app.services.near_vehicle_filter import NearVehicleFilter
from app.services.plate_ocr import PlateOCR
from app.services.vehicle_detector import VehicleDetector
from app.services.video_analyzer import VideoBatchAnalyzer


def _build_source() -> VideoSource | SampleImageSource:
    """Return a VideoSource if the video file exists, else fall back to the image."""
    if VIDEO_SOURCE_PATH.exists():
        return VideoSource(VIDEO_SOURCE_PATH, sample_every_n_frames=FRAME_SAMPLE_INTERVAL)
    return SampleImageSource(SAMPLE_IMAGE_PATH)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    application.state.hydrotest_db.initialize()
    if not os.getenv("PYTEST_CURRENT_TEST"):
        application.state.hydrotest_db.seed_fleet_if_empty()
    source = application.state.detection_pipeline.source
    try:
        yield
    finally:
        # Release the video capture handle on shutdown
        if isinstance(source, VideoSource):
            source.release()


app = FastAPI(
    title="EPS Vehicle Intelligence API",
    description="Real-time vehicle detection, plate OCR, and CNG cylinder hydrotest verification.",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.hydrotest_db = Database()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

pipeline = VehicleDetectionPipeline(
    source=_build_source(),
    detector=VehicleDetector(MODEL_NAME),
    annotator=ImageAnnotator(),
    vehicle_filter=NearVehicleFilter(),
    plate_ocr=PlateOCR(),
)
app.state.detection_pipeline = pipeline
app.state.video_analyzer = VideoBatchAnalyzer(
    pipeline=pipeline,
    database=app.state.hydrotest_db,
)

app.include_router(router)
app.include_router(verify_router)
app.include_router(alerts_router)
app.include_router(video_analysis_router)
