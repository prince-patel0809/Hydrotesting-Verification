from typing import Literal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    x1: float
    y1: float
    x2: float
    y2: float


class PlateRecognition(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal[
        "recognized", "unreadable", "no_candidate", "unavailable", "disabled"
    ]
    candidate_found: bool
    box: BoundingBox | None = None
    localization_method: Literal["contour", "lower_center_fallback"] | None = None
    raw_text: str | None = None
    normalized_text: str | None = None
    india_format_valid: bool = False
    plate_category: str | None = None
    special_number: bool = False
    enhanced_crop: str | None = None
    preprocessing: list[str] = Field(default_factory=list)
    message: str | None = None


class VehicleDetection(BaseModel):
    model_config = ConfigDict(frozen=True)

    vehicle_type: str
    confidence: float
    box: BoundingBox
    area_percent: float
    bottom_position: float
    near_score: float
    plate: PlateRecognition
    vehicle_id: str = ""
    sharpness_score: float = 0


class DetectionSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    confidence_threshold: float = Field(ge=0.05, le=0.95)
    min_area_percent: float = Field(ge=0.05, le=50)
    min_bottom_position: float = Field(ge=0.1, le=1)
    max_detections: int = Field(ge=1, le=30)
    ocr_enabled: bool = True


class DetectionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_image: str
    model: str
    image_width: int
    image_height: int
    detection_count: int
    candidates_before_filter: int
    filtered_out_count: int
    settings: DetectionSettings
    detections: list[VehicleDetection]
    annotated_image: str


class VehicleLogSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    vehicle_id: str
    vehicle_type: str
    confidence: float
    registration: str | None = None
    identified: bool
    plate_status: str
    first_seen: datetime
    last_seen: datetime
    frames_seen: int
    best_frame_number: int
    sharpness_score: float
    detection: VehicleDetection


class VehicleLogRecord(VehicleLogSummary):
    best_frame_image: str
