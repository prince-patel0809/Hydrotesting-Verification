import os
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = API_ROOT.parent

# ---------------------------------------------------------------------------
# Video / image input source
# ---------------------------------------------------------------------------
# Primary live-simulation source: an MP4 video file at the project root or api folder.
# Set VIDEO_SOURCE_PATH to override. Falls back to SAMPLE_IMAGE_PATH for tests.
_video_candidates = [
    PROJECT_ROOT / "video2.mp4",
    API_ROOT / "video2.mp4",
    PROJECT_ROOT / "video.mp4",
    API_ROOT / "video.mp4",
]
_VIDEO_DEFAULT = next((p for p in _video_candidates if p.exists()), PROJECT_ROOT / "video2.mp4")
VIDEO_SOURCE_PATH = Path(os.getenv("VIDEO_SOURCE_PATH", str(_VIDEO_DEFAULT)))

# Legacy single-image fallback used by tests and the HTTP /api/detection endpoint.
_image_candidates = [
    API_ROOT / "image.jpeg",
    PROJECT_ROOT / "image.jpeg",
]
_IMAGE_DEFAULT = next((p for p in _image_candidates if p.exists()), API_ROOT / "image.jpeg")
SAMPLE_IMAGE_PATH = Path(os.getenv("SAMPLE_IMAGE_PATH", str(_IMAGE_DEFAULT)))

# How many raw video frames to skip between frames that are sent to the
# detection pipeline.  At 60 fps, FRAME_SAMPLE_INTERVAL=15 → ~4 processed fps.
# Increase to reduce CPU load; decrease for more temporal detail.
FRAME_SAMPLE_INTERVAL = max(1, int(os.getenv("FRAME_SAMPLE_INTERVAL", "15")))

# Seconds between WebSocket frames dispatched to the frontend.
# This adds an extra wait after pipeline processing so the dashboard doesn't
# update faster than the user can read it.
FRAME_DISPATCH_INTERVAL = max(0.1, float(os.getenv("FRAME_DISPATCH_INTERVAL", "1.0")))

MODEL_NAME = os.getenv("YOLO_MODEL", "yolov8n.pt")
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("YOLO_CONFIDENCE", "0.25"))
MAX_CONCURRENT_PLATE_OCR = max(1, int(os.getenv("MAX_CONCURRENT_PLATE_OCR", "4")))
VEHICLE_CLASSES = frozenset(
    {"bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"}
)
