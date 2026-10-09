# Product overview

## Goal

Build an extensible EPS vehicle-intelligence service that accepts camera or
video frames, identifies vehicles and Indian registration plates, and can
eventually pass recognized registration details to an authorized vehicle
information provider.

## Current MVP

- The API reads a configured sample camera image independently of the web UI.
- YOLO detects vehicle classes; configurable image-space size and vertical
  position heuristics favor nearer vehicles.
- The API limits the number of selected vehicles and returns each result with
  its type, confidence, source-frame box, and near-field measurements.
- OpenCV finds plate-shaped candidate regions within each selected vehicle.
- Plate crops are grayscaled and enhanced before Tesseract OCR.
- Indian registration patterns are checked as a formatting heuristic; OCR is
  not an official registration validation.
- A Tailwind React analyst dashboard presents the uncropped image feed,
  compact identified/review-needed session logs, and a tabbed details dialog.
- Start/Stop controls stream a clearly labeled repeating still-image demo over
  a persistent WebSocket; settings include detection thresholds.
- Per-session IoU matching groups similar detections and retains the sharpest
  annotated frame in an in-memory ledger.
- A separate hydrotest API and dashboard panel check the cylinder due date
  associated with a plate. Expired cylinders create persistent critical
  alerts; near-due cylinders create warnings; unknown records require human
  review.
- Supervisors can acknowledge open alerts. Hydrotest checks and alerts are
  stored in SQLite, while the vehicle registry must be populated from an
  authorized source.

## Not in this MVP

Actual video/camera streaming, robust multi-camera tracking, physical-distance
calibration, official OCR registration validation, an authorized vehicle and
cylinder registry integration, other PUC/insurance/fitness lookups,
authentication, and production deployment are future work. Third-party
lookups must use an authorized provider and an explicit integration contract.
