# Architecture

## Processing flow

```text
Configured sample-image source (replayed for demo)
  -> vehicle detector (YOLO)
  -> near-vehicle filter (area, vertical position, result limit)
  -> plate OCR per selected vehicle
       -> vehicle crop
       -> OpenCV plate-candidate localization or bounded lower-center fallback
       -> grayscale / CLAHE / denoise / adaptive threshold / upscale
       -> Tesseract OCR
       -> Indian-format and special-suffix heuristics
  -> image annotator
  -> FastAPI structured result + annotated image
  -> session vehicle tracker (IoU) and sharpest-frame ledger
  -> WebSocket Start/Stop replay controls and progress/events
  -> Tailwind React dashboard, session logs, and filter controls

Separate hydrotest verification flow:

```text
React hydrotest panel
  -> POST /api/verify (plate)
  -> local SQLite vehicles registry
  -> shared due-date rules
  -> checks history + deduplicated alerts
  -> dashboard/fleet counts and supervisor acknowledgement
```
```

`api/app/pipeline.py` composes the services; the individual services do not
depend on the React app. Plate coordinates are translated from vehicle-crop
coordinates to the original source frame. OCR output is carried by the same
vehicle record as the vehicle detection metadata. The WebSocket replays the
configured still image at intervals as an explicitly labeled demo, assigns
per-session IDs using IoU matching, and updates an in-memory ledger with the
sharpest annotated observation for each ID.

## Service boundaries

- `SampleImageSource.read()` returns a source frame.
- `VehicleDetector.detect(frame, confidence_threshold)` returns all vehicle
  candidates with type, confidence, pixel box, and image-space proximity data.
- `NearVehicleFilter.apply(...)` returns the nearest accepted detections and
  the count filtered out.
- `PlateOCR.recognize(frame, vehicle, enabled)` returns candidate box, OCR
  status, raw/normalized text, enhanced preview, and Indian-format metadata.
- `ImageAnnotator.annotate(frame, detections)` returns the display frame.

## API

- `GET /api/health`: service health.
- `GET /api/video/analysis`: retrieve cached or default full-video timeline analysis.
- `POST /api/video/analyze`: run batch video analysis across `video.mp4` with custom settings.
- `WS /api/video/analyze/ws`: WebSocket channel for streaming live progress of batch video processing.
- `GET /api/detection`: process the configured sample image.
- `WS /api/detection/live`: persistent control channel. On connect it sends
  the preview and `ready`; clients send `start`, `stop`, or `clear_log`, and
  receive status, pipeline progress, frames, and record updates.
- `POST /api/verify`: check a plate against the local hydrotest registry,
  record the result, and create/update an alert for expired or near-due
  cylinders. Missing records/dates return `NEEDS_REVIEW`.
- `GET /api/alerts`: filter and paginate alerts by state and level. Open
  alerts are ordered critical-first and remain until acknowledged.
- `POST /api/alerts/{id}/acknowledge`: acknowledge an alert with an optional
  supervisor note; repeated acknowledgements are idempotent.
- `GET /api/dashboard`: return local-date scan counts, open alerts, recent
  critical-first alerts, and a fleet due-date summary.

Hydrotest checks and alerts are stored in SQLite (`HYDROTEST_DB_PATH`, default
`api/hydrotest.sqlite3`). The `vehicles` table is a local registry and must be
populated by an authorized source. `rules.py` provides the shared expiration
and 30-day warning classification used by plate verification and fleet
summaries. Hydrotest registry verification is independent of the image scan
pipeline; OCR format matching alone does not establish the registry record.

Detection query parameters:

| Parameter | Default | Bounds | Meaning |
| --- | ---: | ---: | --- |
| `confidence` | `0.25` | `0.05`–`0.95` | Minimum YOLO confidence |
| `min_area_percent` | `1.5` | `0.05`–`50` | Minimum vehicle-box area as a percent of the frame |
| `min_bottom_position` | `0.55` | `0.1`–`1` | Minimum box-bottom position as a fraction of image height |
| `max_detections` | `5` | `1`–`30` | Maximum nearest vehicles returned |
| `ocr_enabled` | `true` | boolean | Enable plate localization and OCR |

The detection response contains source/model/image details, active settings,
candidate and filtered counts, the annotated image, and a list of vehicles.
Each vehicle retains its type, confidence, vehicle box, area, bottom position,
near score, and a `plate` object. The plate object includes status, candidate
coordinates, localization method, raw/normalized OCR, format classification,
and an enhanced crop when a plate candidate is found.

The WebSocket session log and IoU tracker are scoped to one connection.
Vehicle IDs are an MVP heuristic; they are not guaranteed to identify a
vehicle across occlusion, camera changes, or reconnects. One-shot HTTP
processing creates an isolated tracker. The feed currently repeats a still
image and is not a live video source.

## Constraints

- Area and vertical position are relative to the image and camera view; they
  are tunable heuristics, not physical distance.
- OCR requires the Tesseract executable on `PATH`. Missing Tesseract is
  represented explicitly in the per-vehicle plate status.
- Registration-format and special-number checks are heuristics, not official
  vehicle-record verification.
