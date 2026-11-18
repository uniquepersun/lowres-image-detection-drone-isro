import { useEffect, useState, useCallback } from "react";
import { apiBase } from "../config";

interface Capture {
  id: string;
  slot: number;
  confidence: number;
  inliers: number;
  ts: number;
  x: number;
  y: number;
  z: number;
  hi_url: string;
  lo_url: string;
  hi_size?: [number, number];
}

// Matches saved by the Jetson: each is a low-res frame (thumbnail) plus the
// full-res frame (click to open). Only frames that matched a reference are saved.
export default function MatchGallery() {
  const [captures, setCaptures] = useState<Capture[]>([]);
  const [online, setOnline] = useState(true);
  const [open, setOpen] = useState<Capture | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/matches/captures?limit=60`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setCaptures(await res.json());
      setOnline(true);
    } catch {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const clearAll = async () => {
    if (captures.length === 0) return;
    if (!window.confirm(`Delete all ${captures.length} saved captures on the Jetson?`)) return;
    setBusy(true);
    try {
      await fetch(`${apiBase()}/matches/captures`, { method: "DELETE" });
      setOpen(null);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const base = apiBase();

  return (
    <div className="bg-hud-panel border border-hud-panelBorder rounded-lg p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${online ? "bg-hud-green" : "bg-hud-red"}`} />
          <span className="text-[10px] tracking-widest text-hud-dim font-data">
            MATCHED CAPTURES ({captures.length})
          </span>
        </div>
        <button
          onClick={clearAll}
          disabled={busy || captures.length === 0}
          className="text-[9px] font-data px-2 py-0.5 rounded border border-hud-panelBorder text-hud-dim hover:text-hud-red hover:border-hud-red disabled:opacity-40 disabled:hover:text-hud-dim disabled:hover:border-hud-panelBorder"
        >
          CLEAR
        </button>
      </div>

      {captures.length === 0 ? (
        <div className="text-[11px] font-data text-hud-dim py-4 text-center">
          {online
            ? "No matches yet. Upload a reference image and point the camera at it."
            : "Can't reach the Jetson."}
        </div>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {captures.map((c) => (
            <button
              key={c.id}
              onClick={() => setOpen(c)}
              className="shrink-0 w-44 text-left rounded border border-hud-panelBorder hover:border-hud-green bg-black/30 overflow-hidden"
            >
              <img
                src={`${base}${c.lo_url}`}
                alt={`match slot ${c.slot}`}
                loading="lazy"
                className="w-full h-24 object-cover"
              />
              <div className="px-1.5 py-1 flex items-center justify-between text-[9px] font-data">
                <span className="text-hud-green font-bold">
                  SLOT {c.slot} · {Math.round(c.confidence * 100)}%
                </span>
                <span className="text-hud-dim">{new Date(c.ts * 1000).toLocaleTimeString()}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* full-res viewer */}
      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-4"
          onClick={() => setOpen(null)}
        >
          <div
            className="max-w-[95vw] max-h-[95vh] flex flex-col gap-2"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={`${base}${open.hi_url}`}
              alt={`full-res match slot ${open.slot}`}
              className="max-w-[95vw] max-h-[85vh] object-contain rounded border border-hud-panelBorder"
            />
            <div className="flex items-center justify-between text-xs font-data text-hud-text">
              <span>
                SLOT {open.slot} · {Math.round(open.confidence * 100)}% · {open.inliers} inliers
                {open.hi_size ? ` · ${open.hi_size[0]}×${open.hi_size[1]}` : ""} · pos x{" "}
                {open.x.toFixed(2)} y {open.y.toFixed(2)} z {open.z.toFixed(2)}
              </span>
              <span className="flex gap-3">
                <a
                  href={`${base}${open.hi_url}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-hud-amber hover:underline"
                >
                  OPEN FULL
                </a>
                <button onClick={() => setOpen(null)} className="text-hud-dim hover:text-hud-text">
                  CLOSE (Esc)
                </button>
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
