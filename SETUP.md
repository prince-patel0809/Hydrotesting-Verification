# Setup and run

This guide covers local development on Windows with PowerShell. The project has
an API in `api/` and a React dashboard in `web/`. During local development, the
dashboard sends HTTP and WebSocket requests through the Vite proxy to the local
API.

## Requirements

- Windows 10 or later
- Python 3.11 and the Python Launcher (`py`)
- Node.js and npm (current Node.js LTS recommended)
- Tesseract OCR (optional; required for plate text recognition)

## Install dependencies

Open two PowerShell terminals in the project root.

In the first terminal, create the API virtual environment and install its
packages:

```powershell
Set-Location .\api
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

In the second terminal, install the frontend packages:

```powershell
Set-Location .\web
npm install
```

## Configure local environment

`web/.env` is read by Vite. The local defaults should be:

```dotenv
VITE_API_BASE_URL=
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

An empty `VITE_API_BASE_URL` makes the dashboard use its own origin. Vite then
proxies `/api` HTTP requests and WebSocket connections to the API target. The
same settings are documented in `web/.env.example`. Restart the Vite server
after changing this file.

The API does not automatically load `api/.env`. To override API settings for a
local run, set the variables in the PowerShell terminal before starting
Uvicorn. For example, from the `api/` directory:

```powershell
$env:SAMPLE_IMAGE_PATH = (Resolve-Path .\image-2.png).Path
```

Useful API variables include `SAMPLE_IMAGE_PATH`, `VIDEO_SOURCE_PATH`,
`YOLO_MODEL`, `YOLO_CONFIDENCE`, `FRAME_SAMPLE_INTERVAL`, and
`FRAME_DISPATCH_INTERVAL`. Defaults are defined in `api/app/core/config.py`.

## Install OCR (optional)

Install Tesseract, for example with Windows Package Manager:

```powershell
winget install --id UB-Mannheim.TesseractOCR
```

Open a new terminal and check that it is on `PATH`:

```powershell
tesseract --version
```

If Tesseract is installed elsewhere, set its path in the same terminal used to
start the API:

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Without Tesseract, vehicle detection still runs and the API reports OCR as
unavailable.

## Start the apps

In the API terminal, from the project root:

```powershell
Set-Location .\api
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

The API uses the configured video source when present, or falls back to its
sample image. To choose the second sample image, set the environment variable
before starting Uvicorn (from the `api/` directory):

```powershell
$env:SAMPLE_IMAGE_PATH = (Resolve-Path .\image-2.png).Path
python -m uvicorn app.main:app --reload
```

In the frontend terminal:

```powershell
Set-Location .\web
npm run dev
```

Open <http://localhost:5173/>. Select **Start service** to run the demo feed
and **Stop service** to stop it. The feed replays the configured sample source;
it is not a live camera stream.

Useful API URLs:

- Health check: <http://localhost:8000/api/health>
- Interactive API documentation: <http://localhost:8000/docs>
- One-shot detection: <http://localhost:8000/api/detection>

The first detection may take longer while Ultralytics downloads model weights
if they are not already cached.

## Use another local API address

To proxy to an API running on another local address or port, update
`VITE_API_PROXY_TARGET` in `web/.env`, for example:

```dotenv
VITE_API_PROXY_TARGET=http://127.0.0.1:8002
```

Keep `VITE_API_BASE_URL` empty when using the Vite proxy, then restart the
frontend dev server. Pointing `VITE_API_BASE_URL` directly at a remote API
bypasses the proxy; that server must allow the frontend origin through CORS and
accept the WebSocket connection.

## Troubleshooting

- **The dashboard cannot connect to the API:** make sure Uvicorn is running on
  port 8000 and check <http://localhost:8000/api/health>. Verify
  `VITE_API_BASE_URL` is empty and `VITE_API_PROXY_TARGET` points to the API;
  restart Vite after changing `.env`.
- **Browser reports a CORS error or the WebSocket fails:** for local use, leave
  `VITE_API_BASE_URL` empty and proxy to the local API. A direct remote API
  connection requires that server to allow the dashboard origin and its
  WebSocket connection.
- **Uvicorn raises an `ArgsKwargs` or `pydantic_core` import error:** from the
  `api/` directory, activate the API environment, reinstall Pydantic and its
  compiled core package together, and restart Uvicorn:

  ```powershell
  .\.venv\Scripts\Activate.ps1
  python -m pip install --no-cache-dir --force-reinstall pydantic pydantic-core
  python -m uvicorn app.main:app --reload
  ```

- **The virtual environment cannot find Python:** install Python 3.11, then
  recreate `api/.venv` using the install steps above.
- **`py` is not recognized:** install Python 3.11 and enable the Python
  Launcher, or use the full path to its executable.
- **OCR reports unavailable:** install Tesseract and put it on `PATH`, or set
  `TESSERACT_CMD` in the API terminal.
- **The configured image cannot be opened:** confirm `SAMPLE_IMAGE_PATH`
  points to an existing image file. Relative paths are interpreted from the
  API process's working directory.

## Optional validation

Run the backend unit tests from `api/`:

```powershell
py -3.11 -m unittest discover -s tests -v
```

Build the frontend from `web/`:

```powershell
npm run build
```
