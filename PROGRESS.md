# Progress

## Current status

**MVP stages 1–3 implemented:** sample-image vehicle detection and configurable
near-field filtering; OpenCV plate-candidate localization/enhancement and
Tesseract OCR with Indian-format metadata; plus a Tailwind analyst dashboard
with Start/Stop replay controls, WebSocket progress, IoU-based session vehicle
IDs, separate result logs, and sharpest-frame retention.

## Remaining

- Test candidate localization and OCR against a varied set of Indian vehicle
  and plate images. The current sample has one prominent rear-facing car and
  is not a complete accuracy benchmark.
- Replace still-image replay with video/camera sources; improve tracking
  beyond the IoU MVP heuristic.
- Add authorized vehicle-record integration and durable session persistence.

## Validation

- `py -3.11 -m unittest discover -s tests -v` — 10 service and WebSocket tests
  passed, including plate localization on both sample images, noisy OCR
  extraction, replay Start/Stop, vehicle tracking, and sharpest-frame retention.
- `npm run build` in `web/` — production build passed.
- `npm audit --audit-level=moderate` in `web/` — no known vulnerabilities.
- Browser smoke check — Image 2 replayed across multiple frames; four repeat
  detections grouped into four IDs, `DL3CCT8408` was surfaced as a
  format-matched read, Stop ended processing, all detail tabs rendered, and
  the 360-pixel mobile viewport had no horizontal overflow.
- `GET /api/detection` on `image-2.png` — 8 vehicle candidates, 4 retained as
  near-field. Tesseract read the foreground registration as `DL3CCT8408` from
  raw OCR `A DL3CCT8408`; the supported Indian format was matched. Vehicles
  without a plate-shaped region report `no_candidate`.
- Tesseract OCR engine 5.4.0 was installed locally for end-to-end verification.
- API parameter check — stricter area filtering and OCR-off behavior returned
  the expected nearby car and `disabled` OCR metadata; invalid confidence was
  rejected with HTTP 422.
