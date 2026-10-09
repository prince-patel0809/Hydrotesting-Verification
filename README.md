# EPS Vehicle Intelligence

A modular vehicle-camera processing MVP. The API currently replays a configured
sample still image as a clearly labeled demo feed, detects nearby vehicles,
tracks repeat detections within a session, and keeps the sharpest frame for
each tracked vehicle. Indian plate candidates are enhanced for OCR. A Tailwind
React dashboard presents the uncropped feed, identified and review-needed logs,
and tabbed per-vehicle details.

## Start the demo

Follow [SETUP.md](SETUP.md) for requirements, installation, optional Tesseract
setup, and full Windows startup instructions. The quick start is to run the API
and web app in separate terminals:

```powershell
cd api
py -3.11 -m pip install -r requirements.txt
py -3.11 -m uvicorn app.main:app --reload
```

```powershell
cd web
npm install
npm run dev
```

Open <http://localhost:5173/> and use **Start service** to begin the repeating
sample-image demo; **Stop service** ends the replay. The API docs are at
<http://localhost:8000/docs>.
Install the Tesseract executable separately and add it to `PATH` to enable OCR;
the API reports an explicit OCR status if it is missing. See [api/README.md](api/README.md)
for setup details and [ARCHITECTURE.md](ARCHITECTURE.md) for the pipeline.
This is not a live camera/video feed yet. IDs use a simple IoU box-matching
heuristic, and the session log is in-memory and cleared when the WebSocket
session ends.

## Project notes

- [PRODUCT.md](PRODUCT.md): product scope and intended users.
- [FEATURES.md](FEATURES.md): implemented behavior and planned stages.
- [ARCHITECTURE.md](ARCHITECTURE.md): services and API result contract.
- [PROGRESS.md](PROGRESS.md): implementation status and validation.
- [AGENTS.md](AGENTS.md): repository guidance, including documentation upkeep.
