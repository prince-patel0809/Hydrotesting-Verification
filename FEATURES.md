# Features and roadmap

## Implemented

- [x] Sample-frame input independent of the React app, replayed as a clearly
  labeled demo feed.
- [x] Second test image at `api/image-2.png` selectable through
  `SAMPLE_IMAGE_PATH`.
- [x] Vehicle detection for supported COCO vehicle classes.
- [x] Configurable confidence threshold.
- [x] Near-field heuristic using vehicle-box area and bottom-of-frame position.
- [x] Configurable maximum number of selected vehicles, ordered by near score.
- [x] Per-vehicle type, confidence, source-image coordinates, area, and
  bottom-position metadata.
- [x] OpenCV vehicle and plate-candidate annotations.
- [x] OpenCV plate candidate localization within vehicle crops.
- [x] Grayscale, contrast enhancement, denoising, adaptive thresholding, and
  upscaling before OCR.
- [x] Tesseract OCR integration and Indian registration-format classification,
  including Bharat-series syntax and a heuristic for special/fancy suffixes.
- [x] Indian registration extraction from noisy OCR output when the
  registration itself matches a supported pattern.
- [x] React controls for confidence, near-field cutoffs, maximum vehicles, and
  enabling/disabling OCR.
- [x] Explicit result status when the plate candidate or OCR runtime is
  unavailable.
- [x] Persistent WebSocket Start/Stop control channel with repeating sample
  image frames and pipeline progress events.
- [x] Per-session IoU-based vehicle IDs to group repeat detections and an
  in-memory ledger retaining each vehicle's sharpest annotated frame.
- [x] Separate identified and review-needed session logs; tabbed per-vehicle
  details for summary, pipeline results, metadata, and report.
- [x] Compact, responsive Tailwind light-theme dashboard with an uncropped
  feed and configurable detection controls.
- [x] OCR strings without a supported Indian format are explicitly labeled
  uncertain rather than shown as verified plates.

## Planned

- [ ] Replace sample-image replay with camera/video frame providers.
- [ ] Improve plate localization using a dedicated license-plate detection
  model and representative Indian plate data.
- [ ] Improve vehicle tracking beyond the current per-session IoU heuristic
  using representative video and occlusion tests.
- [ ] Integrate an authorized vehicle-record/PUC/fitness provider.
- [ ] Add integration tests against real plate images and supported regional
  plate variants.
- [ ] Calibrate image-space near-field heuristics for a specific camera.

## Limits

Nearness is estimated from image-space box area and vertical position. It is
not a distance measurement and should be tuned for the camera scene. Indian
registration regex matches identify plausible formatting only; they do not
confirm that a registration is genuine or currently valid. Fancy-number
recognition is a basic suffix heuristic, not an official government category.
The repeating still, IoU tracker, and in-memory log are demo/MVP mechanisms;
there is no live camera source, durable identity, or persistent session store.
