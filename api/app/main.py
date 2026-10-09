from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import MODEL_NAME, SAMPLE_IMAGE_PATH
from app.pipeline import VehicleDetectionPipeline
from app.services.image_annotator import ImageAnnotator
from app.services.image_source import SampleImageSource
from app.services.near_vehicle_filter import NearVehicleFilter
from app.services.plate_ocr import PlateOCR
from app.services.vehicle_detector import VehicleDetector

app = FastAPI(
    title="Vehicle Detection API",
    description="Detect vehicles in the configured sample image and return an annotated result.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.state.detection_pipeline = VehicleDetectionPipeline(
    source=SampleImageSource(SAMPLE_IMAGE_PATH),
    detector=VehicleDetector(MODEL_NAME),
    annotator=ImageAnnotator(),
    vehicle_filter=NearVehicleFilter(),
    plate_ocr=PlateOCR(),
)

app.include_router(router)
