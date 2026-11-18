import { useState, useRef, useEffect, DragEvent, ChangeEvent } from "react";
import { apiBase } from "../config";

interface Slot {
  file: File | null;
  preview: string | null;
  uploaded: boolean; // this exact file has been sent to the Jetson
}

interface Remote {
  loaded: boolean; // the Jetson holds a reference for this slot
  found: boolean; // currently matching the live camera
  confidence: number;
  inliers: number;
  saved: number; // captures saved for this slot
}

const SLOT_COUNT = 3;
const EMPTY_SLOT: Slot = { file: null, preview: null, uploaded: false };
const EMPTY_REMOTE: Remote = { loaded: false, found: false, confidence: 0, inliers: 0, saved: 0 };

export default function ImageUploader() {
  const [slots, setSlots] = useState<Slot[]>(Array.from({ length: SLOT_COUNT }, () => EMPTY_SLOT));
  const [remote, setRemote] = useState<Remote[]>(Array.from({ length: SLOT_COUNT }, () => EMPTY_REMOTE));
  const [online, setOnline] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeSlotRef = useRef<number>(0);

  // Poll the Jetson for which references it holds and whether they match right now.
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await fetch(`${apiBase()}/matches/status`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!alive) return;
        const next: Remote[] = Array.from({ length: SLOT_COUNT }, () => EMPTY_REMOTE);
        for (const s of data.slots ?? []) {
          const i = Number(s.slot) - 1;
          if (i >= 0 && i < SLOT_COUNT) {
            next[i] = {
              loaded: !!s.loaded,
              found: !!s.found,
              confidence: Number(s.confidence) || 0,
              inliers: Number(s.inliers) || 0,
              saved: Number(s.saved) || 0,
            };
          }
        }
        setRemote(next);
        setOnline(true);
      } catch {
        if (alive) setOnline(false);
      }
    };
    poll();
    const t = setInterval(poll, 1500);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const addFile = (slotIdx: number, file: File) => {
    if (!file.type.startsWith("image/")) return;
    const preview = URL.createObjectURL(file);
    setSlots((prev) => {
      const next = [...prev];
      if (next[slotIdx].preview) URL.revokeObjectURL(next[slotIdx].preview!);
      next[slotIdx] = { file, preview, uploaded: false };
      return next;
    });
  };

  const removeSlot = (slotIdx: number) => {
    setSlots((prev) => {
      const next = [...prev];
      if (next[slotIdx].preview) URL.revokeObjectURL(next[slotIdx].preview!);
      next[slotIdx] = EMPTY_SLOT;
      return next;
    });
    // also clear it on the Jetson so it stops matching against it
    fetch(`${apiBase()}/reference-images/${slotIdx + 1}`, { method: "DELETE" }).catch(() => {});
  };

  const onDrop = (slotIdx: number, e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(null);
    const file = e.dataTransfer.files[0];
    if (file) addFile(slotIdx, file);
  };

  const openPicker = (slotIdx: number) => {
    activeSlotRef.current = slotIdx;
    fileInputRef.current?.click();
  };

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) addFile(activeSlotRef.current, file);
    e.target.value = ""; // allow re-selecting the same file
  };

  const pending = slots.filter((s) => s.file !== null && !s.uploaded).length;

  const uploadAll = async () => {
    if (pending === 0) {
      setResult({ success: false, message: "Add an image to a slot first." });
      return;
    }
    setUploading(true);
    setResult(null);
    const lines: string[] = [];
    let allOk = true;
    const uploadedIdx: number[] = [];
    for (let i = 0; i < slots.length; i++) {
      const s = slots[i];
      if (!s.file || s.uploaded) continue;
      try {
        const form = new FormData();
        form.append("file", s.file, s.file.name);
        const res = await fetch(`${apiBase()}/reference-images/${i + 1}`, { method: "POST", body: form });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          lines.push(`✅ Slot ${i + 1}: ${data.detail ?? "loaded"}`);
          uploadedIdx.push(i);
        } else {
          allOk = false;
          lines.push(`❌ Slot ${i + 1}: ${data.error ?? `HTTP ${res.status}`}`);
        }
      } catch (e: any) {
        allOk = false;
        lines.push(`❌ Slot ${i + 1}: ${e.message ?? "network error"} (is the Jetson reachable?)`);
      }
    }
    if (uploadedIdx.length > 0) {
      setSlots((prev) => prev.map((s, i) => (uploadedIdx.includes(i) ? { ...s, uploaded: true } : s)));
    }
    setResult({ success: allOk, message: lines.join("\n") });
    setUploading(false);
  };

  return (
    <div className="bg-hud-panel border border-hud-panelBorder rounded-lg p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] tracking-widest text-hud-dim">REFERENCE IMAGES → JETSON (LOW-RES MATCH)</div>
        <span
          title={online ? "Jetson reachable" : "Jetson not reachable"}
          className={`h-2 w-2 rounded-full ${online ? "bg-hud-green" : "bg-hud-red"}`}
        />
      </div>

      {/* image slots */}
      <div className="grid grid-cols-3 gap-2">
        {slots.map((slot, idx) => {
          const r = remote[idx];
          const showLoadedOnly = !slot.preview && r.loaded; // Jetson has it, this browser doesn't
          const border = r.found
            ? "border-hud-green bg-hud-green/10"
            : dragOver === idx
            ? "border-hud-amber bg-hud-amber/10 scale-[1.02]"
            : slot.file || showLoadedOnly
            ? "border-hud-panelBorder bg-black/30"
            : "border-hud-panelBorder/50 bg-black/20 hover:border-hud-amber/60 hover:bg-hud-amber/5";
          return (
            <div
              key={idx}
              onDrop={(e) => onDrop(idx, e)}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(idx);
              }}
              onDragLeave={() => setDragOver(null)}
              onClick={() => !slot.file && !showLoadedOnly && openPicker(idx)}
              className={`relative aspect-square rounded border-2 border-dashed transition-all cursor-pointer overflow-hidden ${border}`}
            >
              {slot.preview ? (
                <img src={slot.preview} alt={`slot-${idx + 1}`} className="w-full h-full object-cover" />
              ) : showLoadedOnly ? (
                <div className="w-full h-full flex flex-col items-center justify-center gap-1 select-none">
                  <span className="text-hud-green text-lg">✓</span>
                  <span className="text-[8px] font-data text-hud-dim">LOADED ON JETSON</span>
                </div>
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center gap-1 select-none">
                  <span className="text-hud-panelBorder/60 text-lg">＋</span>
                  <span className="text-[8px] font-data text-hud-dim/60">IMG {idx + 1}</span>
                </div>
              )}

              {(slot.preview || showLoadedOnly) && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeSlot(idx);
                  }}
                  className="absolute top-0.5 right-0.5 w-4 h-4 bg-hud-red/80 hover:bg-hud-red rounded-full flex items-center justify-center text-white text-[9px] font-bold leading-none"
                >
                  ×
                </button>
              )}

              {/* slot number */}
              {(slot.preview || showLoadedOnly) && (
                <span className="absolute bottom-0.5 left-0.5 text-[8px] font-data bg-black/60 text-hud-dim px-1 rounded">
                  {idx + 1}
                </span>
              )}

              {/* state badge */}
              {r.found ? (
                <span className="absolute bottom-0.5 right-0.5 text-[8px] font-data bg-hud-green/90 text-black px-1 rounded font-bold">
                  MATCH {Math.round(r.confidence * 100)}%
                </span>
              ) : slot.file && !slot.uploaded ? (
                <span className="absolute bottom-0.5 right-0.5 text-[8px] font-data bg-hud-amber/90 text-black px-1 rounded">
                  NOT SENT
                </span>
              ) : r.loaded ? (
                <span className="absolute bottom-0.5 right-0.5 text-[8px] font-data bg-black/70 text-hud-amber px-1 rounded">
                  ARMED{r.saved > 0 ? ` · ${r.saved}` : ""}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* hidden file input */}
      <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={onFileChange} />

      {/* Upload button */}
      <button
        onClick={uploadAll}
        disabled={uploading || pending === 0}
        className={`w-full py-1.5 text-xs font-data rounded border transition ${
          uploading || pending === 0
            ? "bg-hud-amber/10 border-hud-amber/30 text-hud-dim cursor-not-allowed"
            : "bg-hud-amber/10 border-hud-amber text-hud-amber hover:bg-hud-amber/20 active:scale-[0.98]"
        }`}
      >
        {uploading ? "UPLOADING..." : `UPLOAD ${pending > 0 ? `(${pending}) ` : ""}→ START MATCHING`}
      </button>

      {/* result message */}
      {result && (
        <div
          className={`text-[9px] font-data px-2 py-1 rounded border leading-snug whitespace-pre-line ${
            result.success
              ? "text-hud-green bg-hud-green/10 border-hud-green/30"
              : "text-hud-red bg-hud-red/10 border-hud-red/30"
          }`}
        >
          {result.message}
        </div>
      )}
    </div>
  );
}
