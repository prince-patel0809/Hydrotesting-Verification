import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  CarFront,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Image as ImageIcon,
  Play,
  ScanLine,
  Settings2,
  ShieldCheck,
  Square,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const PIPELINE = [
  ["loading", "Frame"],
  ["detecting", "Vehicles"],
  ["filtering", "Near field"],
  ["plate_ocr", "Plate OCR"],
  ["annotating", "Review"],
];
const INITIAL_SETTINGS = {
  confidence: 0.25,
  min_area_percent: 1.5,
  min_bottom_position: 0.55,
  max_detections: 5,
  ocr_enabled: true,
};

function mergeRecords(current, summaries, updates) {
  const next = { ...current };
  for (const summary of summaries) {
    next[summary.vehicle_id] = {
      ...next[summary.vehicle_id],
      ...summary,
      best_frame_image: next[summary.vehicle_id]?.best_frame_image ?? null,
    };
  }
  for (const update of updates) {
    next[update.vehicle_id] = { ...next[update.vehicle_id], ...update };
  }
  return next;
}

function plateLabel(record) {
  if (record.identified) return record.registration;
  if (record.plate_status === "no_candidate") return "Plate not visible";
  if (record.plate_status === "disabled") return "OCR disabled";
  if (record.plate_status === "unavailable") return "OCR unavailable";
  if (record.detection?.plate?.normalized_text) return "Not sure";
  return "Could not identify";
}

function DetailDialog({ record, onClose }) {
  const [tab, setTab] = useState("summary");
  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const plate = record.detection.plate;
  const tabs = [
    ["summary", "Summary"],
    ["pipelines", "Pipeline results"],
    ["metadata", "Metadata"],
    ["report", "Report"],
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/40 p-3 backdrop-blur-[2px] sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        aria-labelledby="detail-title"
        aria-modal="true"
        className="my-auto w-full max-w-4xl overflow-hidden rounded-xl border border-white/80 bg-[#faf9f6] shadow-[0_16px_48px_rgba(30,41,34,0.20)]"
        role="dialog"
      >
        <header className="flex items-center justify-between border-b border-[#e9e5dc] px-4 py-3 sm:px-5">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8b9188]">
              Vehicle record · {record.vehicle_id}
            </p>
            <h2 className="mt-1 truncate text-lg font-semibold text-[#303831]" id="detail-title">
              {record.identified ? record.registration : "Plate identification needs review"}
            </h2>
          </div>
          <button
            aria-label="Close vehicle details"
            className="ml-3 rounded-md p-2 text-[#747d75] transition hover:bg-[#efede7] hover:text-[#303831]"
            onClick={onClose}
            type="button"
          >
            <X size={18} />
          </button>
        </header>

        <nav aria-label="Vehicle detail sections" className="flex flex-wrap gap-1 border-b border-[#e9e5dc] px-3 sm:px-5">
          {tabs.map(([id, label]) => (
            <button
              aria-current={tab === id ? "page" : undefined}
              className={`shrink-0 border-b-2 px-3 py-3 text-sm font-medium transition ${
                tab === id
                  ? "border-[#c55b34] text-[#9c482b]"
                  : "border-transparent text-[#747d75] hover:text-[#39423b]"
              }`}
              key={id}
              onClick={() => setTab(id)}
              type="button"
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="max-h-[min(68vh,620px)] overflow-y-auto p-4 sm:p-5">
          {tab === "summary" && (
            <div className="grid gap-4 md:grid-cols-[1.25fr_1fr]">
              <div className="overflow-hidden rounded-lg border border-[#e6e2da] bg-[#eeece6]">
                {record.best_frame_image ? (
                  <img
                    alt={`Sharpest retained frame ${record.best_frame_number} for ${record.vehicle_id}`}
                    className="max-h-[360px] w-full object-contain"
                    src={record.best_frame_image}
                  />
                ) : (
                  <div className="grid min-h-48 place-items-center text-sm text-[#737d74]">
                    Best frame preview is not available.
                  </div>
                )}
              </div>
              <dl className="grid content-start grid-cols-2 gap-2">
                <Metric label="Vehicle type" value={record.vehicle_type} />
                <Metric label="Detection confidence" value={`${(record.confidence * 100).toFixed(1)}%`} />
                <Metric label="Seen in frames" value={record.frames_seen} />
                <Metric label="Sharpest frame" value={`#${record.best_frame_number}`} />
                <Metric label="Sharpness score" value={record.sharpness_score.toFixed(1)} />
                <Metric label="Plate status" value={plate.status.replaceAll("_", " ")} />
              </dl>
            </div>
          )}

          {tab === "pipelines" && (
            <div className="overflow-hidden rounded-lg border border-[#e6e2da] bg-white">
              <div className="grid grid-cols-[minmax(112px,0.7fr)_minmax(0,1fr)] gap-3 border-b border-[#efede8] bg-[#f6f4ef] px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-[#747d75]">
                <span>Stage</span><span>Result</span>
              </div>
              <PipelineRow label="Vehicle detection" value={`${record.vehicle_type} · ${(record.confidence * 100).toFixed(1)}%`} />
              <PipelineRow label="Near-field filter" value={`${record.detection.area_percent.toFixed(1)}% frame area · bottom ${Math.round(record.detection.bottom_position * 100)}%`} />
              <PipelineRow label="Plate localization" value={plate.candidate_found ? plate.localization_method?.replaceAll("_", " ") ?? "Candidate found" : "No plate region found"} />
              <PipelineRow label="Image enhancement" value={plate.preprocessing?.join(" → ") || "Not run"} />
              <PipelineRow label="OCR" value={plate.raw_text ? `Raw: ${plate.raw_text}` : plateLabel(record)} />
              <PipelineRow label="Indian format check" value={record.identified ? `Matched · ${plate.plate_category}` : "Not verified; no plate value inferred"} last />
            </div>
          )}

          {tab === "metadata" && (
            <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <Metric label="Stable vehicle ID" value={record.vehicle_id} mono />
              <Metric label="Class" value={record.vehicle_type} />
              <Metric label="Registration" value={record.registration ?? "Not identified"} mono />
              <Metric label="Source box (px)" value={`${Math.round(record.detection.box.x1)}, ${Math.round(record.detection.box.y1)} → ${Math.round(record.detection.box.x2)}, ${Math.round(record.detection.box.y2)}`} mono />
              <Metric label="Near score" value={record.detection.near_score.toFixed(3)} mono />
              <Metric label="Image-space area" value={`${record.detection.area_percent.toFixed(2)}%`} mono />
              <Metric label="First seen" value={new Date(record.first_seen).toLocaleString()} />
              <Metric label="Last seen" value={new Date(record.last_seen).toLocaleString()} />
              <Metric label="Frames observed" value={record.frames_seen} />
              <Metric label="Best-frame sharpness" value={record.sharpness_score.toFixed(2)} mono />
              <Metric label="Raw OCR" value={plate.raw_text ?? "No text read"} mono />
              <Metric label="Format match" value={record.identified ? "Indian registration pattern" : "No match"} />
            </dl>
          )}

          {tab === "report" && (
            <div className="rounded-lg border border-[#e6e2da] bg-white p-4 text-sm leading-6 text-[#58625a]">
              <div className="mb-3 flex items-center gap-2 font-semibold text-[#39423b]">
                {record.identified ? <ShieldCheck className="text-[#46775b]" size={17} /> : <CircleHelp className="text-[#a36835]" size={17} />}
                {record.identified ? "Pattern-matched plate read" : "Manual review recommended"}
              </div>
              <p>
                {record.identified
                  ? `${record.registration} matches a supported Indian registration format. This is an OCR pattern match only, not official registration verification.`
                  : "The service did not find a confident, format-matched registration for this vehicle. No plate number has been inferred; review the retained frame manually."}
              </p>
              <p className="mt-2 text-xs text-[#828980]">
                Frame #{record.best_frame_number} was retained as the sharpest of {record.frames_seen} repeated sample frames.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value, mono = false }) {
  return (
    <div className="min-w-0 rounded-lg border border-[#e9e5dc] bg-white px-3 py-2.5 shadow-[0_2px_8px_rgba(54,47,34,0.035)]">
      <dt className="text-xs font-medium text-[#848b83]">{label}</dt>
      <dd className={`mt-1 break-words text-sm font-semibold text-[#39423b] ${mono ? "font-mono text-[12px]" : ""}`}>
        {value}
      </dd>
    </div>
  );
}

function PipelineRow({ label, value, last = false }) {
  return (
    <div className={`grid grid-cols-[minmax(112px,0.7fr)_minmax(0,1fr)] gap-3 px-3 py-2.5 text-sm ${last ? "" : "border-b border-[#efede8]"}`}>
      <span className="font-medium text-[#697269]">{label}</span>
      <span className="break-words text-[#424c44]">{value}</span>
    </div>
  );
}

function LogEntry({ record, onSelect }) {
  const identified = record.identified;
  return (
    <button
      className="group flex w-full items-center gap-3 border-b border-[#eeebe5] px-3 py-2.5 text-left transition hover:bg-[#f6f4ef] focus-visible:outline-2 focus-visible:outline-[#c55b34] last:border-b-0"
      onClick={() => onSelect(record.vehicle_id)}
      type="button"
    >
      <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg border ${
        identified
          ? "border-[#d8e5d9] bg-[#eff5ef] text-[#46775b]"
          : "border-[#eadfd2] bg-[#f8f2e9] text-[#9c6b3b]"
      }`}>
        {identified ? <ShieldCheck size={17} /> : <CarFront size={17} />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold text-[#384139]">
            {identified ? record.registration : `${record.vehicle_type} · ${plateLabel(record)}`}
          </span>
          <span className={`hidden shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium sm:inline-flex ${
            identified ? "bg-[#eff5ef] text-[#46775b]" : "bg-[#f8f2e9] text-[#936739]"
          }`}>
            {identified ? "IDENTIFIED" : "REVIEW"}
          </span>
        </div>
        <p className="mt-0.5 truncate text-xs text-[#7b847b]">
          {record.vehicle_type} · ID {record.vehicle_id} · {record.frames_seen} frame{record.frames_seen === 1 ? "" : "s"}
        </p>
      </div>
      <div className="hidden text-right sm:block">
        <p className="font-mono text-xs text-[#4e594f]">{record.sharpness_score.toFixed(1)} sharpness</p>
        <p className="mt-0.5 text-[11px] text-[#858c84]">Best frame #{record.best_frame_number}</p>
      </div>
      <ChevronRight className="shrink-0 text-[#a4aaa2] transition group-hover:translate-x-0.5 group-hover:text-[#69736a]" size={17} />
    </button>
  );
}

function App() {
  const socketRef = useRef(null);
  const [connection, setConnection] = useState("connecting");
  const [streamStatus, setStreamStatus] = useState("idle");
  const [source, setSource] = useState(null);
  const [preview, setPreview] = useState(null);
  const [frameImage, setFrameImage] = useState(null);
  const [frameNumber, setFrameNumber] = useState(0);
  const [progress, setProgress] = useState({ stage: "loading", detail: "Waiting to start", percent: 0 });
  const [settings, setSettings] = useState(INITIAL_SETTINGS);
  const [records, setRecords] = useState({});
  const [selectedId, setSelectedId] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    const base = new URL(API_BASE || window.location.origin, window.location.origin);
    const socketProtocol = base.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${socketProtocol}//${base.host}${base.pathname.replace(/\/$/, "")}/api/detection/live`,
    );
    socketRef.current = socket;

    socket.onopen = () => {
      if (mounted) setConnection("connected");
    };
    socket.onmessage = (message) => {
      if (!mounted) return;
      const event = JSON.parse(message.data);
      if (event.type === "ready") {
        setSource({ name: event.source_image, width: event.width, height: event.height });
        setPreview(event.preview);
      } else if (event.type === "status") {
        setStreamStatus(event.status);
        if (event.status === "log_cleared") setRecords({});
      } else if (event.type === "progress") {
        setProgress(event);
      } else if (event.type === "frame") {
        setFrameNumber(event.frame_number);
        setSource({ name: event.source_image, width: event.image_width, height: event.image_height });
        if (event.annotated_image) setFrameImage(event.annotated_image);
        setRecords((current) => mergeRecords(current, event.records, event.record_updates));
        setProgress({ stage: "complete", detail: `Frame ${event.frame_number} reviewed`, percent: 100 });
        setError("");
      } else if (event.type === "error") {
        setError(event.detail);
      }
    };
    socket.onerror = () => {
      if (mounted) setConnection("error");
    };
    socket.onclose = () => {
      if (mounted) {
        setConnection("closed");
        setStreamStatus("idle");
      }
    };

    return () => {
      mounted = false;
      socket.close();
    };
  }, []);

  const recordList = useMemo(
    () => Object.values(records).sort((first, second) => second.last_seen.localeCompare(first.last_seen)),
    [records],
  );
  const identifiedRecords = recordList.filter((record) => record.identified);
  const reviewRecords = recordList.filter((record) => !record.identified);
  const selectedRecord = selectedId ? records[selectedId] : null;
  const activeStage = PIPELINE.findIndex(([stage]) => stage === progress.stage);
  const isRunning = streamStatus === "running";

  const startService = useCallback(() => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      setError("The API live connection is not available. Check that the FastAPI service is running.");
      return;
    }
    setError("");
    setFrameNumber(0);
    setFrameImage(null);
    setProgress({ stage: "loading", detail: "Starting sample-image replay", percent: 0 });
    socketRef.current.send(JSON.stringify({ action: "start", ...settings, interval_seconds: 1.5 }));
  }, [settings]);

  const stopService = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ action: "stop" }));
    }
  }, []);

  const clearLog = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ action: "clear_log" }));
    }
    setSelectedId(null);
  }, []);

  const updateSetting = (key, value) => {
    setSettings((current) => ({ ...current, [key]: value }));
  };

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1440px] px-3 pb-5 sm:px-5 lg:px-7">
      <header className="flex min-h-14 items-center justify-between border-b border-[#e4e1d9]">
        <a aria-label="EPS vehicle review home" className="flex items-center gap-2.5 text-sm font-semibold tracking-wide text-[#384139]" href="/">
          <span className="grid h-8 w-8 place-items-center rounded-[10px] border border-white/80 bg-[#f1f3ee] text-[#406c56] shadow-[2px_2px_6px_rgba(61,72,60,0.10),-2px_-2px_6px_rgba(255,255,255,0.8)]">
            <CarFront size={18} />
          </span>
          EPS <span className="font-normal text-[#a0a69e]">/</span> VEHICLE REVIEW
        </a>
        <div className="flex items-center gap-2 text-xs font-medium text-[#677168]">
          {connection === "connected" ? <Wifi className="text-[#46775b]" size={15} /> : <WifiOff className="text-[#9b6d49]" size={15} />}
          <span className="hidden sm:inline">{connection === "connected" ? "API CONNECTED" : "API DISCONNECTED"}</span>
          <span className={`h-2 w-2 rounded-full ${isRunning ? "animate-pulse bg-[#c55b34]" : connection === "connected" ? "bg-[#62926d]" : "bg-[#b58869]"}`} />
        </div>
      </header>

      <section className="flex flex-wrap items-center justify-between gap-3 py-4">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-[#818981]">Camera analysis <span className="px-1 text-[#c5beb2">/</span> India</p>
          <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-[#303831] sm:text-2xl">Vehicle activity</h1>
          <p className="mt-1 text-sm text-[#707a71]">Review identified plates and vehicles that need a closer look.</p>
        </div>
        <div className="flex items-center gap-2">
          <details className="relative">
            <summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-lg border border-[#deded5] bg-[#f7f6f2] px-3 text-sm font-medium text-[#58635a] shadow-[2px_2px_7px_rgba(54,62,51,0.07),-2px_-2px_7px_rgba(255,255,255,0.75)] hover:bg-white">
              <Settings2 size={16} /> <span className="hidden sm:inline">Settings</span>
            </summary>
            <div className="absolute right-0 z-30 mt-2 w-[min(350px,calc(100vw-24px))] rounded-xl border border-[#e4e1d9] bg-[#faf9f6] p-4 shadow-[0_12px_32px_rgba(35,44,36,0.16)]">
              <div className="mb-3 border-b border-[#eae7df] pb-2">
                <h2 className="text-sm font-semibold text-[#39433b]">Detection settings</h2>
                <p className="mt-1 text-xs text-[#7c857c]">Changes apply when you start the service.</p>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <SettingSlider label="Min vehicle area" value={settings.min_area_percent} min="0.2" max="12" step="0.1" display={`${settings.min_area_percent.toFixed(1)}%`} onChange={(value) => updateSetting("min_area_percent", value)} />
                <SettingSlider label="Near-field position" value={settings.min_bottom_position} min="0.2" max="0.9" step="0.01" display={`${Math.round(settings.min_bottom_position * 100)}%`} onChange={(value) => updateSetting("min_bottom_position", value)} />
                <SettingSlider label="Detector confidence" value={settings.confidence} min="0.05" max="0.9" step="0.01" display={`${Math.round(settings.confidence * 100)}%`} onChange={(value) => updateSetting("confidence", value)} />
                <SettingSlider label="Maximum vehicles" value={settings.max_detections} min="1" max="20" step="1" display={settings.max_detections} onChange={(value) => updateSetting("max_detections", value)} />
              </div>
              <label className="mt-3 flex items-center justify-between border-t border-[#eae7df] pt-3 text-sm text-[#4f5b51]">
                Indian plate OCR
                <input checked={settings.ocr_enabled} className="h-4 w-4 accent-[#c55b34]" onChange={(event) => updateSetting("ocr_enabled", event.target.checked)} type="checkbox" />
              </label>
            </div>
          </details>
          <button
            className={`inline-flex min-h-10 items-center gap-2 rounded-lg px-4 text-sm font-semibold text-white shadow-[0_3px_9px_rgba(42,50,41,0.12)] transition disabled:cursor-not-allowed disabled:opacity-50 ${
              isRunning ? "bg-[#606e63] hover:bg-[#4e5a51]" : "bg-[#c45c32] hover:bg-[#a94b28]"
            }`}
            disabled={connection !== "connected"}
            onClick={isRunning ? stopService : startService}
            type="button"
          >
            {isRunning ? <Square size={14} fill="currentColor" /> : <Play size={15} fill="currentColor" />}
            {isRunning ? "Stop service" : "Start service"}
          </button>
        </div>
      </section>

      {error && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-[#eed9cf] bg-[#fbf3ed] px-3 py-2 text-sm text-[#9c482b]" role="alert">
          <AlertCircle className="mt-0.5 shrink-0" size={16} />
          <span className="flex-1">{error}</span>
          <button aria-label="Dismiss error" className="rounded p-0.5 hover:bg-[#f5e6dd]" onClick={() => setError("")} type="button"><X size={16} /></button>
        </div>
      )}

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.65fr)_minmax(280px,0.8fr)]">
        <div className="overflow-hidden rounded-xl border border-white/80 bg-[#faf9f6] p-2.5 shadow-[3px_4px_13px_rgba(57,62,49,0.08),-3px_-3px_12px_rgba(255,255,255,0.8)] sm:p-3">
          <div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-[#424d44]"><ImageIcon className="text-[#53745d]" size={16} /> Sample camera feed</div>
            <div className="flex items-center gap-2">
              <span className="rounded-full border border-[#e8dfcc] bg-[#f7f2e6] px-2.5 py-1 text-[11px] font-medium text-[#896b3d]">DEMO · REPEATING STILL</span>
              {isRunning && <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#a44c30]"><i className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#c45c32]" /> REC</span>}
            </div>
          </div>
          <div className="relative grid aspect-video min-h-[205px] w-full place-items-center overflow-hidden rounded-lg border border-[#e5e2d9] bg-[#eeece6] sm:min-h-[245px] xl:min-h-[300px]">
            {(frameImage ?? preview) ? (
              <img
                alt={`Full uncropped ${source?.name ?? "sample camera"} frame`}
                className="absolute inset-0 h-full w-full object-contain"
                src={frameImage ?? preview}
              />
            ) : (
              <div className="flex flex-col items-center gap-2 text-[#788279]">
                <ImageIcon size={26} />
                <span className="text-sm">Waiting for sample frame</span>
              </div>
            )}
            {isRunning && (
              <>
                <div className="pointer-events-none absolute inset-x-0 top-0 h-12 animate-scan bg-gradient-to-b from-transparent via-[#69a981]/10 to-transparent" />
                <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-white/60 bg-[#f7f5ef]/90 px-2 py-1 font-mono text-[11px] font-medium text-[#48554b] shadow-sm">
                  SAMPLE LOOP · FRAME {String(frameNumber).padStart(4, "0")}
                </div>
              </>
            )}
            {source && <span className="absolute bottom-2 right-2 rounded bg-[#f8f7f2]/90 px-2 py-1 font-mono text-[10px] text-[#586159]">{source.width} × {source.height}</span>}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-1 pt-2 text-xs text-[#737d74]">
            <span className="min-w-0 truncate"><span className="font-medium text-[#515d53]">Source</span> · {source?.name ?? "Connecting to API…"}</span>
            <span className="inline-flex items-center gap-1"><Clock3 size={13} /> {isRunning ? `Frame ${frameNumber} · replaying sample` : "Feed stopped"}</span>
          </div>
        </div>

        <aside className="rounded-xl border border-white/80 bg-[#f4f3ed] p-3 shadow-[3px_4px_13px_rgba(57,62,49,0.07),-3px_-3px_12px_rgba(255,255,255,0.8)] sm:p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#414c43]">Session activity</h2>
            <span className="text-[11px] text-[#818980]">In-memory log</span>
          </div>
          <div className="mt-3 grid grid-cols-3 divide-x divide-[#e0ded5] rounded-lg border border-white/70 bg-[#faf9f5] py-2.5 shadow-[inset_1px_1px_4px_rgba(62,68,57,0.035)]">
            <CountMetric label="Tracked" value={recordList.length} />
            <CountMetric label="Identified" value={identifiedRecords.length} />
            <CountMetric label="Review" value={reviewRecords.length} />
          </div>
          <div className="mt-3 border-t border-[#dfded5] pt-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-[#5b665d]">Pipeline activity</span>
              <span className="font-mono text-[11px] text-[#7d867e]">{isRunning ? `${progress.percent}%` : "—"}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[#e4e2d9]">
              <div className="h-full rounded-full bg-[#68896e] transition-all duration-300" style={{ width: `${isRunning ? progress.percent : 0}%` }} />
            </div>
            <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1">
              {PIPELINE.map(([id, label], index) => {
                const done = isRunning && (progress.stage === "complete" || index < activeStage);
                const active = isRunning && progress.stage === id;
                return (
                  <span className={`inline-flex items-center gap-1 text-[11px] ${active ? "font-semibold text-[#a34d31]" : done ? "text-[#55765c]" : "text-[#9ba198]"}`} key={id}>
                    {done ? <Check size={11} /> : <i className={`h-1.5 w-1.5 rounded-full ${active ? "bg-[#c45c32]" : "bg-[#c7c9c1]"}`} />}
                    {label}
                  </span>
                );
              })}
            </div>
            <p className="mt-2 min-h-5 text-xs leading-5 text-[#707a71]">{progress.detail}</p>
          </div>
          <div className="mt-2 flex items-center justify-between border-t border-[#dfded5] pt-2 text-[11px] text-[#788178]">
            <span className="truncate">{connection === "connected" ? "Live service connected" : "Waiting for API connection"}</span>
            <button className="ml-2 shrink-0 font-medium text-[#9a553a] transition hover:text-[#733d2b] disabled:cursor-not-allowed disabled:opacity-45" disabled={recordList.length === 0} onClick={clearLog} type="button">Clear log</button>
          </div>
        </aside>
      </section>

      <section className="mt-4">
        <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-[#364038] sm:text-lg">Vehicle log</h2>
            <p className="mt-0.5 text-xs text-[#788178]">Repeated detections are grouped by tracked vehicle ID; the sharpest observed frame is retained.</p>
          </div>
          <span className="text-xs text-[#858c84]">{recordList.length} unique vehicle{recordList.length === 1 ? "" : "s"} · {frameNumber} frame{frameNumber === 1 ? "" : "s"} processed</span>
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <LogSection
            icon={<ShieldCheck size={16} />}
            records={identifiedRecords}
            title="Plate identified"
            tone="green"
            onSelect={setSelectedId}
          />
          <LogSection
            icon={<CircleHelp size={16} />}
            records={reviewRecords}
            title="Vehicle detected · plate not verified"
            tone="amber"
            onSelect={setSelectedId}
          />
        </div>
      </section>

      <footer className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-[#e1ded6] py-2.5 text-[11px] text-[#858c84]">
        <span>DEMO INPUT · {source?.name ?? "sample frame"}</span>
        <span>Still-image replay only · ready to replace with a camera/video source</span>
      </footer>

      {selectedRecord && <DetailDialog onClose={() => setSelectedId(null)} record={selectedRecord} />}
    </main>
  );
}

function CountMetric({ label, value }) {
  return (
    <div className="px-1 text-center">
      <p className="text-[10px] font-medium text-[#7c857c] sm:text-xs">{label}</p>
      <p className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-[#39443b]">{value}</p>
    </div>
  );
}

function SettingSlider({ label, value, min, max, step, display, onChange }) {
  return (
    <label className="min-w-0">
      <span className="flex items-center justify-between gap-1 text-xs text-[#606b61]">
        {label}<strong className="font-mono text-[#a24c31]">{display}</strong>
      </span>
      <input className="mt-2 w-full accent-[#c45c32]" max={max} min={min} onChange={(event) => onChange(Number(event.target.value))} step={step} type="range" value={value} />
    </label>
  );
}

function LogSection({ icon, records, title, tone, onSelect }) {
  const identified = tone === "green";
  return (
    <section className="overflow-hidden rounded-xl border border-white/80 bg-[#faf9f6] shadow-[2px_3px_11px_rgba(57,62,49,0.06),-2px_-2px_10px_rgba(255,255,255,0.8)]">
      <header className="flex items-center justify-between border-b border-[#e9e6de] px-3 py-2.5">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-[#424c44]">{icon}{title}</h3>
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${identified ? "bg-[#edf4ed] text-[#477452]" : "bg-[#f7f0e7] text-[#91683d]"}`}>{records.length}</span>
      </header>
      {records.length ? (
        <div className="max-h-[300px] overflow-y-auto">
          {records.map((record) => <LogEntry key={record.vehicle_id} onSelect={onSelect} record={record} />)}
        </div>
      ) : (
        <div className="flex min-h-[82px] items-center gap-3 px-4 text-sm text-[#7b857b]">
          {identified ? <ScanLine className="text-[#909c90]" size={18} /> : <CircleHelp className="text-[#a19378]" size={18} />}
          <span>{identified ? "Verified-format reads will appear here." : "Uncertain or missing plate reads will appear here."}</span>
        </div>
      )}
    </section>
  );
}

export default App;
