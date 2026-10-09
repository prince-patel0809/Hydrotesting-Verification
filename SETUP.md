# Setup and running the apps

This guide covers local development on Windows using PowerShell. The project
has two apps: a FastAPI backend in `api/` and a React/Vite frontend in `web/`.
The dashboard talks to the API through a Vite proxy, including its WebSocket
connection.

## Requirements

- Windows 10 or later
- Python 3.11
- Node.js and npm (use a current Node.js LTS release)
- Tesseract OCR (optional, but required to read plate text)

## Install dependencies

Open two PowerShell terminals in the project root.

In the first terminal, create the API virtual environment and install Python
packages:

```powershell
Set-Location .\api
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell prevents activation because of its execution policy, either
allow activation for your user or run the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

In the second terminal, install the web dependencies:

```powershell
Set-Location .\web
npm install
```

## Install OCR (optional)

Install the Tesseract executable, for example with Windows Package Manager:

```powershell
winget install --id UB-Mannheim.TesseractOCR
```

Open a new terminal after installation and check that `tesseract` is on `PATH`:

```powershell
tesseract --version
```

If it is installed somewhere not on `PATH`, set `TESSERACT_CMD` in the API
terminal to the full executable path, for example:

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Without Tesseract, vehicle detection still runs, and the API reports OCR as
unavailable rather than inventing a plate result.

## Start the API and web app

Start the API in the first terminal. From the project root:

```powershell
Set-Location .\api
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

By default, the API uses `api/image.jpeg`. To use the second supplied image,
set the sample path before starting Uvicorn:

```powershell
$env:SAMPLE_IMAGE_PATH = (Resolve-Path .\image-2.png).Path
python -m uvicorn app.main:app --reload
```

Run that from the `api/` directory, or set `$env:SAMPLE_IMAGE_PATH` to the
absolute path to the image. The environment variable applies only to the
current PowerShell terminal.

Start the web app in the second terminal:

```powershell
Set-Location .\web
npm run dev
```

Open <http://localhost:5173/>. Select **Start service** to replay the
configured still image as a demo feed; use **Stop service** to stop it. The
feed is not a live camera or video stream.

Useful API URLs:

- Health check: <http://localhost:8000/api/health>
- Interactive API documentation: <http://localhost:8000/docs>
- One-shot detection endpoint: <http://localhost:8000/api/detection>

The first detection may take longer while Ultralytics downloads model weights
if they are not already cached locally.

## Configure the API

These environment variables are optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SAMPLE_IMAGE_PATH` | `api/image.jpeg` | Image used as the demo frame source |
| `YOLO_MODEL` | `yolov8n.pt` | Ultralytics model name or model path |
| `YOLO_CONFIDENCE` | `0.25` | Default detector confidence threshold |
| `TESSERACT_CMD` | `tesseract` on `PATH` | Path to the Tesseract executable |

For the frontend, `web/.env.example` documents `VITE_API_BASE_URL`. Leave it
empty for the default local Vite proxy to `http://127.0.0.1:8000`.

## Run the tests and production build

Run the backend tests from the `api/` directory:

```powershell
py -3.11 -m unittest discover -s tests -v
```

Build the frontend from the `web/` directory:

```powershell
npm run build
```

## Troubleshooting

- **The dashboard says the API is disconnected:** start the API and check
  <http://localhost:8000/api/health>.
- **PowerShell says `py` is not recognized:** install Python 3.11 and enable
  the Python Launcher, or use the full path to your Python 3.11 executable.
- **OCR reports unavailable:** verify Tesseract is installed and on `PATH`, or
  set `TESSERACT_CMD` in the same terminal where Uvicorn is started.
- **A configured image cannot be opened:** verify `SAMPLE_IMAGE_PATH` points
  to an existing image file before starting the API.
