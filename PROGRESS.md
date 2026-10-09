# Progress

## Current status

**MVP stages 1–6 implemented:** Batch video analyzer (`VideoBatchAnalyzer`)
processing entire MP4 video files in one pass with tracked vehicle state;
interactive video simulation timeline player in the React dashboard with scrubber,
Play/Pause, frame stepping, and variable speed; live on-frame vehicle HUD with
instant CNG cylinder hydrotest verification and supervisor alert management; and a
complete searchable vehicle audit ledger with "Jump to Frame" seeking.

## Remaining

- Test candidate localization and OCR against a varied set of Indian vehicle
  and plate images.
- Connect live RTSP/CSI camera frame streams beyond local video/image files.
- Add authorized vehicle-record integration and durable session persistence.
- Populate the hydrotest vehicle registry from an authorized cylinder-data
  provider; the current app uses the local SQLite registry only.

## Validation

- `py -3.11 -m unittest discover -s tests -v` — 10 service and WebSocket tests
  passed, including plate localization on both sample images, noisy OCR
  extraction, replay Start/Stop, vehicle tracking, and sharpest-frame retention.
- `npm run build` in `web/` — production build passed.
- `npm run build` in `web/` — hydrotest verification and alert panel compiled.
- `py -3.11 -m pytest tests -q` in `api/` — 20 backend tests passed.
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
