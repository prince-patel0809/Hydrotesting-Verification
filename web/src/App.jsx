import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Calendar,
  CarFront,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  FastForward,
  Filter,
  Flame,
  Gauge,
  HelpCircle,
  Image as ImageIcon,
  Loader2,
  Maximize2,
  Pause,
  Play,
  RefreshCw,
  Rewind,
  RotateCcw,
  ScanLine,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  Square,
  Truck,
  Video,
  Volume2,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const STATUS_CONFIG = {
  VALID: {
    label: "VALID",
    color: "bg-emerald-50 text-emerald-700 border-emerald-200",
    badge: "bg-emerald-600 text-white",
    icon: ShieldCheck,
    border: "border-emerald-500",
  },
  EXPIRING_SOON: {
    label: "EXPIRING SOON",
    color: "bg-amber-50 text-amber-800 border-amber-200",
    badge: "bg-amber-500 text-white",
    icon: AlertTriangle,
    border: "border-amber-500",
  },
  EXPIRED: {
    label: "CRITICAL EXPIRED",
    color: "bg-rose-50 text-rose-700 border-rose-200",
    badge: "bg-rose-600 text-white",
    icon: ShieldAlert,
    border: "border-rose-500",
  },
  NEEDS_REVIEW: {
    label: "NEEDS REVIEW",
    color: "bg-orange-50 text-orange-800 border-orange-200",
    badge: "bg-orange-500 text-white",
    icon: CircleHelp,
    border: "border-orange-400",
  },
  UNAVAILABLE: {
    label: "UNAVAILABLE",
    color: "bg-slate-50 text-slate-700 border-slate-200",
    badge: "bg-slate-500 text-white",
    icon: HelpCircle,
    border: "border-slate-400",
  },
};

function formatTime(seconds) {
  if (isNaN(seconds) || seconds == null) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function App() {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeProgress, setAnalyzeProgress] = useState({ current: 0, total: 0, stage: "", percent: 0 });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const [filterQuery, setFilterQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [error, setError] = useState("");

  // Playback state
  const [currentFrameIdx, setCurrentFrameIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [isLooping, setIsLooping] = useState(true);
  const playTimerRef = useRef(null);

  // Settings for re-analysis
  const [settings, setSettings] = useState({
    confidence: 0.20,
    min_area_percent: 0.8,
    min_bottom_position: 0.25,
    max_detections: 8,
    ocr_enabled: true,
    sample_fps: 1.5,
    max_frames: 120,
  });

  // Fetch initial or cached video analysis
  const loadInitialAnalysis = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/video/analysis`);
      if (!res.ok) {
        throw new Error(`Failed to load video analysis (HTTP ${res.status})`);
      }
      const data = await res.json();
      setAnalysis(data);
      setCurrentFrameIdx(0);
    } catch (err) {
      setError(err.message || "Failed to load video analysis.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInitialAnalysis();
  }, [loadInitialAnalysis]);

  // Run full batch video analysis over WebSocket
  const startFullAnalysis = useCallback(() => {
    setAnalyzing(true);
    setSettingsOpen(false);
    setError("");
    setIsPlaying(false);
    setAnalyzeProgress({ current: 0, total: 0, stage: "Connecting to analyzer...", percent: 0 });

    const base = new URL(API_BASE || window.location.origin, window.location.origin);
    const socketProtocol = base.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${socketProtocol}//${base.host}${base.pathname.replace(/\/$/, "")}/api/video/analyze/ws`
    );

    socket.onopen = () => {
      socket.send(JSON.stringify(settings));
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "progress") {
          setAnalyzeProgress({
            current: msg.current_frame,
            total: msg.total_frames,
            stage: msg.stage,
            percent: msg.percent,
          });
        } else if (msg.type === "complete") {
          setAnalysis(msg.result);
          setCurrentFrameIdx(0);
          setAnalyzing(false);
          socket.close();
        } else if (msg.type === "error") {
          setError(msg.detail);
          setAnalyzing(false);
          socket.close();
        }
      } catch (err) {
        console.error("WS Parse error:", err);
      }
    };

    socket.onerror = () => {
      setError("WebSocket connection failed during analysis.");
      setAnalyzing(false);
    };

    socket.onclose = () => {
      setAnalyzing(false);
    };
  }, [settings]);

  // Playback timer loop
  useEffect(() => {
    if (!isPlaying || !analysis?.frames?.length) {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
      return;
    }

    const intervalMs = Math.max(50, 1000 / (analysis.settings?.sample_fps || 1.5) / playbackSpeed);

    playTimerRef.current = setInterval(() => {
      setCurrentFrameIdx((prev) => {
        if (prev >= analysis.frames.length - 1) {
          if (isLooping) return 0;
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, intervalMs);

    return () => {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    };
  }, [isPlaying, analysis, playbackSpeed, isLooping]);

  // Keyboard shortcuts (Space to play/pause, Left/Right to step)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.code === "Space") {
        e.preventDefault();
        setIsPlaying((prev) => !prev);
      } else if (e.code === "ArrowLeft") {
        e.preventDefault();
        setIsPlaying(false);
        setCurrentFrameIdx((prev) => Math.max(0, prev - 1));
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        setIsPlaying(false);
        setCurrentFrameIdx((prev) => Math.min((analysis?.frames?.length || 1) - 1, prev + 1));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [analysis]);

  const currentFrame = analysis?.frames?.[currentFrameIdx] ?? null;
  const currentDetections = currentFrame?.detections ?? [];

  // Acknowledge alert helper
  const acknowledgeAlert = async (alertId, note = "") => {
    try {
      const res = await fetch(`${API_BASE}/api/alerts/${alertId}/acknowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: note || "Supervisor reviewed via Dashboard" }),
      });
      if (res.ok) {
        // Refresh analysis/alert state
        loadInitialAnalysis();
      }
    } catch (err) {
      console.error("Alert ack error:", err);
    }
  };

  // Filtered vehicles ledger
  const filteredVehicles = useMemo(() => {
    if (!analysis?.vehicles) return [];
    return analysis.vehicles.filter((v) => {
      const q = filterQuery.toLowerCase().trim();
      const matchQuery =
        !q ||
        v.vehicle_id?.toLowerCase().includes(q) ||
        v.vehicle_type?.toLowerCase().includes(q) ||
        v.registration?.toLowerCase().includes(q) ||
        v.hydrotest?.plate?.toLowerCase().includes(q) ||
        v.hydrotest?.owner?.toLowerCase().includes(q);

      const status = v.hydrotest?.status ?? (v.identified ? "VALID" : "NEEDS_REVIEW");
      const matchStatus = statusFilter === "ALL" || status === statusFilter;

      return matchQuery && matchStatus;
    });
  }, [analysis, filterQuery, statusFilter]);

  // Jump to specific frame
  const jumpToFrame = (frameNumberOrIndex) => {
    if (!analysis?.frames) return;
    const idx = analysis.frames.findIndex(
      (f) => f.frame_index === frameNumberOrIndex || f.video_frame_number === frameNumberOrIndex
    );
    if (idx !== -1) {
      setCurrentFrameIdx(idx);
      setIsPlaying(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f7f6f2] text-[#2d342f] font-sans antialiased">
      {/* Top Header */}
      <header className="sticky top-0 z-40 border-b border-[#e5e1d8] bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1520px] items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#2e4033] text-white shadow-sm">
              <CarFront size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm tracking-tight text-[#1e2a22]">EPS HYDROTEST</span>
                <span className="rounded bg-[#ebe8df] px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-[#636c64]">
                  INTELLIGENCE
                </span>
              </div>
              <p className="text-[11px] text-[#747e76] hidden sm:block">
                Vehicle Video Analysis &amp; CNG Cylinder Verification
              </p>
            </div>
          </div>

          {/* Action Bar */}
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setSettingsOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-[#dcd7cc] bg-white px-3 py-1.5 text-xs font-semibold text-[#48534a] shadow-sm hover:bg-[#faf9f6] transition"
            >
              <Settings2 size={14} />
              <span>Analysis Config</span>
            </button>

            <button
              onClick={startFullAnalysis}
              disabled={analyzing}
              className="flex items-center gap-2 rounded-lg bg-[#c45c32] px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-[#ad4e27] transition disabled:opacity-50"
            >
              {analyzing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              <span>{analyzing ? "Analyzing Video..." : "Re-Analyze Video"}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="mx-auto max-w-[1520px] px-3 py-4 sm:px-6 space-y-4">
        {error && (
          <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-800">
            <div className="flex items-center gap-2">
              <AlertCircle size={16} className="text-rose-600 shrink-0" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError("")} className="hover:opacity-75">
              <X size={14} />
            </button>
          </div>
        )}

        {/* Top KPI Metrics Bar */}
        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
          <KPICard
            label="Vehicles Detected"
            value={analysis?.hydrotest_summary?.total_unique_vehicles ?? 0}
            sub={`${analysis?.sampled_frames_count ?? 0} frames analyzed`}
            icon={CarFront}
            tone="default"
          />
          <KPICard
            label="CNG Valid"
            value={analysis?.hydrotest_summary?.valid ?? 0}
            sub="Certified cylinders"
            icon={ShieldCheck}
            tone="emerald"
          />
          <KPICard
            label="Expired / Critical"
            value={analysis?.hydrotest_summary?.expired ?? 0}
            sub="Do Not Fill Alert"
            icon={ShieldAlert}
            tone="rose"
          />
          <KPICard
            label="Expiring Soon"
            value={analysis?.hydrotest_summary?.expiring_soon ?? 0}
            sub="Due within 30 days"
            icon={AlertTriangle}
            tone="amber"
          />
          <KPICard
            label="Review Needed"
            value={analysis?.hydrotest_summary?.needs_review ?? 0}
            sub="Unregistered / Unverified"
            icon={CircleHelp}
            tone="orange"
          />
        </section>

        {/* Main Video Simulation & Active Frame Vehicles Grid */}
        <section className="grid gap-4 lg:grid-cols-12">
          {/* Video Timeline Player Screen (8 cols) */}
          <div className="lg:col-span-8 flex flex-col rounded-2xl border border-[#e2ded5] bg-white p-3.5 shadow-sm">
            {/* Player Title & Mode */}
            <div className="mb-2.5 flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <Video size={16} className="text-[#3c6b4d]" />
                <h2 className="text-sm font-bold text-[#273229]">
                  Video Simulation Feed
                </h2>
                <span className="rounded-full bg-emerald-100 text-emerald-800 px-2 py-0.5 text-[10px] font-bold">
                  PROCESSED TIMELINE
                </span>
              </div>
              <div className="text-xs font-mono font-semibold text-[#5d6860]">
                {formatTime(currentFrame?.timestamp_sec ?? 0)} / {formatTime(analysis?.duration_sec ?? 0)}
              </div>
            </div>

            {/* Video Canvas / Image Screen */}
            <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-black flex items-center justify-center shadow-inner">
              {loading || analyzing ? (
                <div className="flex flex-col items-center gap-3 text-white">
                  <Loader2 size={36} className="animate-spin text-[#c45c32]" />
                  <p className="text-xs font-medium tracking-wide">
                    {analyzing ? analyzeProgress.stage || "Processing frames..." : "Loading video simulation..."}
                  </p>
                  {analyzing && (
                    <div className="w-48 h-1.5 bg-white/20 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#c45c32] transition-all duration-300"
                        style={{ width: `${analyzeProgress.percent}%` }}
                      />
                    </div>
                  )}
                </div>
              ) : currentFrame?.image_base64 ? (
                <img
                  src={currentFrame.image_base64}
                  alt={`Frame ${currentFrame.frame_index}`}
                  className="h-full w-full object-contain select-none"
                />
              ) : (
                <div className="text-slate-400 text-xs">No frame data available</div>
              )}

              {/* On-Screen HUD Overlay */}
              <div className="pointer-events-none absolute top-3 left-3 flex flex-wrap gap-2">
                <span className="rounded-md bg-black/70 px-2.5 py-1 font-mono text-[11px] font-semibold text-white backdrop-blur-md">
                  FRAME #{String(currentFrameIdx + 1).padStart(3, "0")} / {analysis?.frames?.length ?? 0}
                </span>
                <span className="rounded-md bg-black/70 px-2.5 py-1 text-[11px] font-semibold text-emerald-400 backdrop-blur-md flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-ping inline-block" />
                  {currentDetections.length} VEHICLES IN VIEW
                </span>
              </div>
            </div>

            {/* Timeline Scrubber Slider */}
            <div className="mt-3 px-1 space-y-1">
              <div className="relative flex items-center">
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, (analysis?.frames?.length || 1) - 1)}
                  value={currentFrameIdx}
                  onChange={(e) => {
                    setIsPlaying(false);
                    setCurrentFrameIdx(Number(e.target.value));
                  }}
                  className="w-full accent-[#c45c32] h-2 bg-[#eae7de] rounded-lg cursor-pointer transition-all"
                />
              </div>

              {/* Player Controls Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-[#525e55]">
                {/* Play / Step Buttons */}
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => {
                      setIsPlaying(false);
                      setCurrentFrameIdx(0);
                    }}
                    title="Rewind to start"
                    className="p-1.5 rounded-lg hover:bg-[#f0ede6] text-[#4d5750]"
                  >
                    <RotateCcw size={15} />
                  </button>
                  <button
                    onClick={() => {
                      setIsPlaying(false);
                      setCurrentFrameIdx((prev) => Math.max(0, prev - 1));
                    }}
                    title="Previous frame"
                    className="p-1.5 rounded-lg hover:bg-[#f0ede6] text-[#4d5750]"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <button
                    onClick={() => setIsPlaying((prev) => !prev)}
                    className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#2e4033] text-white hover:bg-[#202d24] transition shadow-sm"
                  >
                    {isPlaying ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" />}
                  </button>
                  <button
                    onClick={() => {
                      setIsPlaying(false);
                      setCurrentFrameIdx((prev) => Math.min((analysis?.frames?.length || 1) - 1, prev + 1));
                    }}
                    title="Next frame"
                    className="p-1.5 rounded-lg hover:bg-[#f0ede6] text-[#4d5750]"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>

                {/* Speed and Loop Controls */}
                <div className="flex items-center gap-2">
                  <div className="flex items-center rounded-lg bg-[#f0ede6] p-0.5 text-[11px] font-semibold">
                    {[0.5, 1.0, 2.0, 4.0].map((spd) => (
                      <button
                        key={spd}
                        onClick={() => setPlaybackSpeed(spd)}
                        className={`rounded-md px-2 py-0.5 transition ${
                          playbackSpeed === spd ? "bg-white text-[#202d24] shadow-xs" : "text-[#717b73] hover:text-[#202d24]"
                        }`}
                      >
                        {spd}x
                      </button>
                    ))}
                  </div>

                  <button
                    onClick={() => setIsLooping((prev) => !prev)}
                    className={`rounded-md px-2 py-1 text-[11px] font-semibold transition border ${
                      isLooping ? "bg-emerald-50 text-emerald-800 border-emerald-300" : "bg-white text-[#717b73] border-[#e2ded5]"
                    }`}
                  >
                    LOOP {isLooping ? "ON" : "OFF"}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Active Frame Vehicles & Live Hydrotest Verification (4 cols) */}
          <div className="lg:col-span-4 flex flex-col rounded-2xl border border-[#e2ded5] bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between border-b border-[#f0ece5] pb-2.5">
              <div>
                <h3 className="font-bold text-sm text-[#242f27]">Frame Vehicles &amp; Hydrotest</h3>
                <p className="text-[11px] text-[#707c73]">Visible in current frame ({currentDetections.length})</p>
              </div>
              <span className="rounded-full bg-[#f2efe8] px-2 py-0.5 font-mono text-[10px] font-bold text-[#556157]">
                {formatTime(currentFrame?.timestamp_sec ?? 0)}
              </span>
            </div>

            {/* List of active vehicles */}
            <div className="flex-1 space-y-2.5 overflow-y-auto max-h-[440px] pr-1">
              {currentDetections.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center text-[#818c83]">
                  <ScanLine size={32} className="stroke-1 mb-2 opacity-50" />
                  <p className="text-xs font-medium">No vehicles in near field</p>
                  <p className="text-[11px] text-[#a1aaa2] mt-0.5">Scrub timeline to see tracked vehicles</p>
                </div>
              ) : (
                currentDetections.map((d) => {
                  const ht = d.hydrotest;
                  const status = ht?.status ?? (d.plate?.india_format_valid ? "VALID" : "NEEDS_REVIEW");
                  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.NEEDS_REVIEW;
                  const StatusIcon = cfg.icon;

                  return (
                    <div
                      key={d.vehicle_id}
                      className={`rounded-xl border p-3 transition hover:shadow-md ${cfg.color} ${cfg.border} bg-opacity-40`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white shadow-xs">
                            <Truck size={14} className="text-[#3c4a3f]" />
                          </div>
                          <div>
                            <span className="font-bold text-xs text-[#1e2820]">{d.vehicle_id}</span>
                            <span className="text-[10px] text-[#637066] ml-1.5 uppercase font-semibold">
                              {d.vehicle_type} ({(d.confidence * 100).toFixed(0)}%)
                            </span>
                          </div>
                        </div>

                        <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${cfg.badge}`}>
                          {cfg.label}
                        </span>
                      </div>

                      {/* Plate and Hydrotest Info */}
                      <div className="mt-2.5 rounded-lg bg-white/80 p-2 text-xs space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-semibold text-[#667268]">Plate OCR:</span>
                          <span className="font-mono font-bold text-xs text-[#1e2a22]">
                            {d.plate?.normalized_text || d.plate?.raw_text || "Unrecognized"}
                          </span>
                        </div>

                        {ht && (
                          <>
                            {ht.owner && (
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="text-[#748177]">Owner:</span>
                                <span className="font-medium truncate max-w-[140px]">{ht.owner}</span>
                              </div>
                            )}
                            {ht.next_due_date && (
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="text-[#748177]">Due Date:</span>
                                <span className="font-medium">{ht.next_due_date}</span>
                              </div>
                            )}
                            {ht.message && (
                              <p className="text-[10px] leading-tight text-[#525f54] pt-0.5 border-t border-black/5">
                                {ht.message}
                              </p>
                            )}
                          </>
                        )}
                      </div>

                      {/* Alert acknowledgment button if critical alert */}
                      {ht?.alert && !ht.alert.acknowledged && (
                        <div className="mt-2 flex items-center justify-between rounded-md bg-rose-100 p-1.5 text-[10px] text-rose-800">
                          <span className="font-semibold">Action Required</span>
                          <button
                            onClick={() => acknowledgeAlert(ht.alert.id)}
                            className="rounded bg-rose-600 px-2 py-0.5 font-bold text-white hover:bg-rose-700 transition"
                          >
                            Acknowledge
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>

        {/* All Tracked Vehicles Table & Audit Ledger */}
        <section className="rounded-2xl border border-[#e2ded5] bg-white p-4 shadow-sm space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#f0ece5] pb-3">
            <div>
              <h3 className="font-bold text-base text-[#242f27]">Complete Video Vehicle Ledger</h3>
              <p className="text-xs text-[#707c73]">
                Summary of all {analysis?.vehicles?.length ?? 0} unique vehicles tracked throughout the video
              </p>
            </div>

            {/* Filter and Search */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#8b968e]" />
                <input
                  type="text"
                  placeholder="Search vehicle ID, plate, owner..."
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                  className="rounded-lg border border-[#ded9cf] bg-[#faf9f6] pl-8 pr-3 py-1.5 text-xs text-[#2b352e] outline-none focus:border-[#c45c32] focus:bg-white transition"
                />
              </div>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="rounded-lg border border-[#ded9cf] bg-[#faf9f6] px-2.5 py-1.5 text-xs font-semibold text-[#48534a] outline-none focus:border-[#c45c32]"
              >
                <option value="ALL">All Statuses</option>
                <option value="VALID">Valid</option>
                <option value="EXPIRED">Expired</option>
                <option value="EXPIRING_SOON">Expiring Soon</option>
                <option value="NEEDS_REVIEW">Needs Review</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-[#414d43]">
              <thead className="bg-[#faf9f6] text-[11px] uppercase font-bold text-[#727d74] border-b border-[#eae6de]">
                <tr>
                  <th className="py-2.5 px-3">Vehicle ID</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">License Plate</th>
                  <th className="py-2.5 px-3">Hydrotest Status</th>
                  <th className="py-2.5 px-3">Owner / Certificate</th>
                  <th className="py-2.5 px-3">Due Date</th>
                  <th className="py-2.5 px-3 text-right">Video Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f2efe8]">
                {filteredVehicles.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-8 text-xs text-[#8c978e]">
                      No vehicle records matched your filter.
                    </td>
                  </tr>
                ) : (
                  filteredVehicles.map((veh) => {
                    const ht = veh.hydrotest;
                    const status = ht?.status ?? (veh.identified ? "VALID" : "NEEDS_REVIEW");
                    const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.NEEDS_REVIEW;

                    return (
                      <tr key={veh.vehicle_id} className="hover:bg-[#faf9f6] transition">
                        <td className="py-2.5 px-3 font-mono font-bold text-[#1f2921]">
                          {veh.vehicle_id}
                        </td>
                        <td className="py-2.5 px-3 capitalize">
                          {veh.vehicle_type}
                        </td>
                        <td className="py-2.5 px-3 font-mono font-semibold">
                          {veh.registration || veh.detection?.plate?.normalized_text || veh.detection?.plate?.raw_text || (
                            <span className="text-[#a0aaa2] italic font-sans">Unverified</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${cfg.badge}`}>
                            {cfg.label}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 truncate max-w-[160px]">
                          {ht?.owner ?? "Fleet Record Unregistered"}
                        </td>
                        <td className="py-2.5 px-3">
                          {ht?.next_due_date ?? "—"}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <button
                            onClick={() => jumpToFrame(veh.first_seen_frame ?? veh.best_frame_number ?? 0)}
                            className="inline-flex items-center gap-1 rounded bg-[#f0ece5] hover:bg-[#c45c32] hover:text-white px-2 py-1 text-[11px] font-semibold text-[#48544a] transition"
                          >
                            <Play size={10} fill="currentColor" />
                            <span>Jump to Frame</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {/* Analysis Settings Modal */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl border border-[#e2ded5] bg-white p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#f0ece5] pb-3">
              <div className="flex items-center gap-2">
                <Sliders size={18} className="text-[#c45c32]" />
                <h3 className="font-bold text-sm text-[#242f27]">Batch Video Analysis Settings</h3>
              </div>
              <button onClick={() => setSettingsOpen(false)} className="text-[#717b73] hover:text-black">
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 text-xs text-[#525e55]">
              <div>
                <label className="flex justify-between font-semibold">
                  <span>Sample Rate (Frames Per Second)</span>
                  <span className="font-mono text-[#c45c32]">{settings.sample_fps} fps</span>
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="5.0"
                  step="0.5"
                  value={settings.sample_fps}
                  onChange={(e) => setSettings({ ...settings, sample_fps: Number(e.target.value) })}
                  className="w-full accent-[#c45c32] mt-1"
                />
                <p className="text-[10px] text-[#8e9890] mt-0.5">
                  1.5 fps = ~190 frames for 2-minute video. Higher = more detail but longer analysis.
                </p>
              </div>

              <div>
                <label className="flex justify-between font-semibold">
                  <span>YOLO Detection Confidence</span>
                  <span className="font-mono text-[#c45c32]">{(settings.confidence * 100).toFixed(0)}%</span>
                </label>
                <input
                  type="range"
                  min="0.10"
                  max="0.80"
                  step="0.05"
                  value={settings.confidence}
                  onChange={(e) => setSettings({ ...settings, confidence: Number(e.target.value) })}
                  className="w-full accent-[#c45c32] mt-1"
                />
              </div>

              <div>
                <label className="flex justify-between font-semibold">
                  <span>Max Frames to Analyze</span>
                  <span className="font-mono text-[#c45c32]">{settings.max_frames || "Full Video"}</span>
                </label>
                <input
                  type="range"
                  min="30"
                  max="300"
                  step="10"
                  value={settings.max_frames || 120}
                  onChange={(e) => setSettings({ ...settings, max_frames: Number(e.target.value) })}
                  className="w-full accent-[#c45c32] mt-1"
                />
              </div>

              <label className="flex items-center justify-between pt-2 border-t border-[#f0ece5]">
                <span className="font-semibold">Enable Tesseract Indian Plate OCR</span>
                <input
                  type="checkbox"
                  checked={settings.ocr_enabled}
                  onChange={(e) => setSettings({ ...settings, ocr_enabled: e.target.checked })}
                  className="h-4 w-4 accent-[#c45c32]"
                />
              </label>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-[#f0ece5]">
              <button
                onClick={() => setSettingsOpen(false)}
                className="rounded-lg px-3 py-1.5 text-xs font-semibold text-[#525e55] hover:bg-[#f0ede6]"
              >
                Cancel
              </button>
              <button
                onClick={startFullAnalysis}
                className="rounded-lg bg-[#c45c32] px-4 py-1.5 text-xs font-semibold text-white hover:bg-[#ad4e27] transition"
              >
                Start Analysis
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function KPICard({ label, value, sub, icon: Icon, tone = "default" }) {
  const tones = {
    default: "bg-white text-[#2a342c] border-[#e2ded5]",
    emerald: "bg-emerald-50/70 text-emerald-950 border-emerald-200",
    rose: "bg-rose-50/70 text-rose-950 border-rose-200",
    amber: "bg-amber-50/70 text-amber-950 border-amber-200",
    orange: "bg-orange-50/70 text-orange-950 border-orange-200",
  };

  const iconTones = {
    default: "text-[#3c4a3f] bg-[#f0ede6]",
    emerald: "text-emerald-700 bg-emerald-100",
    rose: "text-rose-700 bg-rose-100",
    amber: "text-amber-700 bg-amber-100",
    orange: "text-orange-700 bg-orange-100",
  };

  return (
    <div className={`rounded-2xl border p-3.5 shadow-xs transition ${tones[tone] || tones.default}`}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wider text-[#68746a]">{label}</span>
        <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${iconTones[tone] || iconTones.default}`}>
          <Icon size={14} />
        </div>
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="font-mono text-2xl font-bold tracking-tight">{value}</span>
      </div>
      <p className="mt-0.5 text-[10px] text-[#717d73] truncate">{sub}</p>
    </div>
  );
}
