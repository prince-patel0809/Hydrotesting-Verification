import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import app
from app.models.detection import DetectionSettings
from app.pipeline import VehicleDetectionPipeline
from app.services.image_annotator import ImageAnnotator
from app.services.image_source import SampleImageSource
from app.services.near_vehicle_filter import NearVehicleFilter
from app.services.plate_ocr import PlateOCR
from app.services.vehicle_detector import VehicleDetector
from app.services.video_analyzer import VideoBatchAnalyzer


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    video_file = tmp_path / "test_sim.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_file), fourcc, 10.0, (160, 120))
    for i in range(20):
        # Create dummy frame with changing content
        frame = np.full((120, 160, 3), fill_value=i * 10, dtype=np.uint8)
        out.write(frame)
    out.release()
    return video_file


def test_video_batch_analyzer_processes_video(sample_video: Path, tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.initialize()

    pipeline = VehicleDetectionPipeline(
        source=SampleImageSource(sample_video),
        detector=VehicleDetector("yolov8n.pt"),
        annotator=ImageAnnotator(),
        vehicle_filter=NearVehicleFilter(),
        plate_ocr=PlateOCR(),
    )
    analyzer = VideoBatchAnalyzer(pipeline=pipeline, database=db)

    settings = DetectionSettings(
        confidence_threshold=0.25,
        min_area_percent=0.5,
        min_bottom_position=0.2,
        max_detections=5,
        ocr_enabled=True,
    )

    progress_stages = []

    def on_progress(curr, total, stage, pct):
        progress_stages.append((curr, total, pct))

    result = analyzer.analyze_video(
        sample_video,
        settings,
        sample_fps=5.0,
        progress_callback=on_progress,
    )

    assert result.total_video_frames == 20
    assert result.sampled_frames_count > 0
    assert len(result.frames) == result.sampled_frames_count
    assert "total_unique_vehicles" in result.hydrotest_summary
    assert len(progress_stages) > 0
