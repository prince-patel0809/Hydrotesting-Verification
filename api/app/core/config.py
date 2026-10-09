import os
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_IMAGE_PATH = Path(os.getenv("SAMPLE_IMAGE_PATH", str(API_ROOT / "image.jpeg")))
MODEL_NAME = os.getenv("YOLO_MODEL", "yolov8n.pt")
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("YOLO_CONFIDENCE", "0.25"))
VEHICLE_CLASSES = frozenset(
    {"bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"}
)
