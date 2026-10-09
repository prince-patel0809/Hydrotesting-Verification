# Project guidance

## What this project is

EPS Vehicle Intelligence is an MVP for a camera-to-vehicle-information
pipeline. The current implementation processes one configured sample image,
detects nearby vehicles, localizes plate-shaped regions, prepares enhanced
grayscale crops, and attempts Indian registration plate OCR. It does not yet
connect to a vehicle-record, PUC, insurance, or fitness service.

## Engineering guidelines

- Keep input, vehicle detection, near-field filtering, plate OCR, annotation,
  and future record lookup as separate services with explicit data contracts.
- Preserve vehicle type, detection confidence, source-frame bounding box,
  near-field measurements, and plate/OCR metadata together for each vehicle.
- Keep camera/sample image input independent of the React client.
- Treat repeating sample-still replay as a demo adapter, not a live-video
  source.
- Keep WebSocket controls/progress separate from the detection pipeline; scope
  tracker and session-ledger state to the active session.
- Treat IoU IDs and sharpness ranking as MVP heuristics; do not present them
  as durable identity or calibrated image quality.
- Keep filter thresholds configurable through the API and web dashboard.
- Treat area and vertical position as configurable image-space heuristics, not
  calibrated physical distance.
- Do not claim an Indian registration is valid just because OCR returned text.
  Keep format matching explicit, report raw and normalized OCR separately, and
  label unverified formats as unvalidated.
- Surface missing optional OCR software in the result; do not fail vehicle
  detection or silently return success-shaped OCR data.
- Mark OCR as recognized only when its normalized text matches the supported
  Indian registration shape. Display other OCR output as uncertain; never
  repair or invent a registration value to make it fit.
- Keep the analyst UI compact, responsive, accessible, and light-themed. Avoid
  horizontal overflow and show actual pipeline stage progress over WebSocket
  without changing the result contract.
- Prefer small, focused changes and validate the relevant API, UI build, and
  service behavior.

## Documentation upkeep

When changing product scope, a feature, an API contract, architecture, or a
project-wide guideline, update the relevant root Markdown documents in the
same change:

- `PRODUCT.md` for product goals and scope.
- `FEATURES.md` for current or planned behavior.
- `ARCHITECTURE.md` for service boundaries, data flow, and API contracts.
- `PROGRESS.md` for implementation status and validation.
- `AGENTS.md` when engineering or documentation guidance changes.
- `README.md` for setup, entry points, and user-facing overview.
- Reflect user-requested behavior and scope changes across these documents;
  distinguish sample replay and in-memory state from future camera/video and
  persistent-storage implementations.

Do not mark planned or externally dependent work as implemented.
