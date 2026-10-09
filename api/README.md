# Vehicle detection API

This FastAPI service currently replays a configured sample still image as a
stand-in for camera/video frames. It detects traffic-vehicle classes with
Ultralytics YOLOv8, filters out distant vehicles, localizes plate-shaped
regions with OpenCV, and reads them with Tesseract OCR. OCR crops are
grayscaled, contrast-enhanced, denoised, thresholded, and enlarged before
recognition. The React app displays an uncropped annotated feed and groups
repeat observations using per-WebSocket IoU tracking.

## Run the API

From the `api` directory, create and activate a virtual environment, then run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for the interactive API docs. The first request to `GET /api/detection` downloads the `yolov8n.pt` model
weights if they are not already cached. `GET /api/health` checks that the API
is running.

The dashboard uses `WS /api/detection/live` as a persistent Start/Stop control
channel. It first sends a preview and `ready` event; the client can then send
`start` with detection settings, `stop`, or `clear_log`. While running, the API
streams progress, annotated frames, and session-log updates. The configured
still image repeats at 1.5-second intervals by default; this is a demo feed,
not live video. Vehicle IDs and the sharpest-frame ledger are scoped to the
WebSocket connection and are not persisted. `GET /api/detection` remains
available for one-shot processing.

Install the Tesseract OCR executable and ensure `tesseract` is on `PATH`
(Windows: `winget install --id UB-Mannheim.TesseractOCR`). Set `TESSERACT_CMD`
if it is installed outside `PATH`. If it is unavailable, vehicle detection
still works and the plate metadata reports OCR as unavailable. The visual
settings can be sent as query parameters, for example:

```text
/api/detection?confidence=0.25&min_area_percent=1.5&min_bottom_position=0.55&max_detections=5&ocr_enabled=true
```

The sample image path, model, and confidence threshold can be changed with
`SAMPLE_IMAGE_PATH`, `YOLO_MODEL`, and `YOLO_CONFIDENCE` environment variables.
`TESSERACT_CMD` can point to a custom Tesseract executable.

To run the API on the second supplied image (`api/image-2.png`) from
PowerShell, set `SAMPLE_IMAGE_PATH` to its path before starting Uvicorn. For
example, from this directory:

```powershell
$env:SAMPLE_IMAGE_PATH = (Resolve-Path .\image-2.png).Path
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
python -m uvicorn app.main:app --reload
```

## Pipeline boundaries

`SampleImageSource` supplies a frame, `VehicleDetector` returns vehicle types,
confidence scores and pixel bounding boxes, `NearVehicleFilter` selects nearby
vehicles, `PlateOCR` localizes a plate-shaped region and returns OCR plus Indian
registration-pattern metadata, and `ImageAnnotator` produces the visual result.
`VehicleDetectionPipeline` composes these independent steps. PUC/vehicle-record
lookups remain a future stage.
