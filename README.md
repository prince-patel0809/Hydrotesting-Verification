# EPS Vehicle Intelligence

A modular vehicle-camera processing MVP. The API currently replays a configured
sample still image as a clearly labeled demo feed, detects nearby vehicles,
tracks repeat detections within a session, and keeps the sharpest frame for
each tracked vehicle. Indian plate candidates are enhanced for OCR. A Tailwind
React dashboard presents the uncropped feed, identified and review-needed logs,
tabbed per-vehicle details, and hydrotest verification with a fleet summary and
supervisor alert review.

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

## Hydrotest verification API

The backend also exposes a hydrotest check and supervisor alert API. It looks
up a supplied plate in the local SQLite `vehicles` registry; an unknown plate
or missing/invalid due date returns `NEEDS_REVIEW`, never `VALID`. Set
`HYDROTEST_DB_PATH` to choose the database file. The default database is
`api/hydrotest.sqlite3`; populate its `vehicles` table from an authorized
vehicle/cylinder data source before using verification at a pump.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/verify` | Check `{ "plate": "DL01AB1234" }`; returns `VALID`, `EXPIRING_SOON`, `EXPIRED`, or `NEEDS_REVIEW`, and an alert summary when required |
| `GET` | `/api/alerts` | List alerts with `state=open\|acknowledged\|all`, optional `level`, `page`, and `page_size` |
| `POST` | `/api/alerts/{id}/acknowledge` | Acknowledge an alert with optional `{ "note": "..." }` |
| `GET` | `/api/dashboard` | Return today's verification counts, open alerts, fleet due-date summary, upcoming cylinders, and `all_clear` |

`EXPIRED` raises a deduplicated critical alert and instructs operators not to
fill. `EXPIRING_SOON` creates a warning; `VALID` creates no alert. Open alerts
remain visible until acknowledged. Threshold classification is shared between
verification and fleet summary; due dates within 30 days are categorized as
expiring soon. These endpoints do not alter or replace the image scan pipeline.
The web dashboard includes a plate verification form, status result, today's
verification counts, fleet due-date summary, and open-alert acknowledgement.

### Implementation tracker

| Feature | Status |
| --- | --- |
| Alerts | Done |

### Work log

- Added persistent hydrotest verification, deduplicated critical/warning alerts, acknowledgement, and dashboard summaries.

Run the backend tests (including hydrotest API coverage) from `api/` with
`py -3.11 -m pytest tests -q`.
