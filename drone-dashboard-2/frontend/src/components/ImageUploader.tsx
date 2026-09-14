import { useState, useRef, DragEvent, ChangeEvent } from "react";

interface Slot {
  file: File | null;
  preview: string | null;
}

const EMPTY_SLOT: Slot = { file: null, preview: null };

export default function ImageUploader() {
  const [slots, setSlots] = useState<Slot[]>([EMPTY_SLOT, EMPTY_SLOT, EMPTY_SLOT]);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeSlotRef = useRef<number>(0);

  const addFile = (slotIdx: number, file: File) => {
    if (!file.type.startsWith("image/")) return;
    const preview = URL.createObjectURL(file);
    setSlots((prev) => {
      const next = [...prev];
      // revoke old preview to avoid memory leak
      if (next[slotIdx].preview) URL.revokeObjectURL(next[slotIdx].preview!);
      next[slotIdx] = { file, preview };
      return next;
    });
  };

  const removeSlot = (slotIdx: number) => {
    setSlots((prev) => {
      const next = [...prev];
      if (next[slotIdx].preview) URL.revokeObjectURL(next[slotIdx].preview!);
      next[slotIdx] = { file: null, preview: null };
      return next;
    });
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
    // reset so same file can be re-selected
    e.target.value = "";
  };

  const uploadAll = async () => {
    const filled = slots.filter((s) => s.file !== null);
    if (filled.length === 0) {
      setResult({ success: false, message: "Please add at least one image." });
      return;
    }
    setUploading(true);
    setResult(null);
    try {
      const form = new FormData();
      filled.forEach(({ file }) => form.append("images", file!, file!.name));
      const res = await fetch("/api/save-images", { method: "POST", body: form });
      const data = await res.json();
      if (res.ok && data.success) {
        setResult({ success: true, message: `✅ Got ${data.count} features to search for.` });
      } else {
        setResult({ success: false, message: `❌ ${data.error || "Upload failed"}` });
      }
    } catch (e: any) {
      setResult({ success: false, message: `❌ ${e.message}` });
    } finally {
      setUploading(false);
    }
  };

  const filledCount = slots.filter((s) => s.file !== null).length;

  return (
    <div className="bg-hud-panel border border-hud-panelBorder rounded-lg p-3 flex flex-col gap-2">
      <div className="text-[10px] tracking-widest text-hud-dim">REFERENCE IMAGES → /Users/bikash/image_search/reference</div>

      {/* 3 image slots */}
      <div className="grid grid-cols-3 gap-2">
        {slots.map((slot, idx) => (
          <div
            key={idx}
            onDrop={(e) => onDrop(idx, e)}
            onDragOver={(e) => { e.preventDefault(); setDragOver(idx); }}
            onDragLeave={() => setDragOver(null)}
            onClick={() => !slot.file && openPicker(idx)}
            className={`relative aspect-square rounded border-2 border-dashed transition-all cursor-pointer overflow-hidden
              ${dragOver === idx
                ? "border-hud-amber bg-hud-amber/10 scale-[1.02]"
                : slot.file
                ? "border-hud-panelBorder bg-black/30"
                : "border-hud-panelBorder/50 bg-black/20 hover:border-hud-amber/60 hover:bg-hud-amber/5"
              }`}
          >
            {slot.preview ? (
              <>
                <img
                  src={slot.preview}
                  alt={`slot-${idx}`}
                  className="w-full h-full object-cover"
                />
                {/* remove button */}
                <button
                  onClick={(e) => { e.stopPropagation(); removeSlot(idx); }}
                  className="absolute top-0.5 right-0.5 w-4 h-4 bg-hud-red/80 hover:bg-hud-red rounded-full flex items-center justify-center text-white text-[9px] font-bold leading-none"
                >
                  ×
                </button>
                {/* slot number badge */}
                <span className="absolute bottom-0.5 left-0.5 text-[8px] font-data bg-black/60 text-hud-dim px-1 rounded">
                  {idx + 1}
                </span>
              </>
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center gap-1 select-none">
                <span className="text-hud-panelBorder/60 text-lg">＋</span>
                <span className="text-[8px] font-data text-hud-dim/60">IMG {idx + 1}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={onFileChange}
      />

      {/* Upload button */}
      <button
        onClick={uploadAll}
        disabled={uploading || filledCount === 0}
        className={`w-full py-1.5 text-xs font-data rounded border transition ${
          uploading || filledCount === 0
            ? "bg-hud-amber/10 border-hud-amber/30 text-hud-dim cursor-not-allowed"
            : "bg-hud-amber/10 border-hud-amber text-hud-amber hover:bg-hud-amber/20 active:scale-[0.98]"
        }`}
      >
        {uploading ? "UPLOADING..." : `UPLOAD ${filledCount > 0 ? `(${filledCount})` : ""} → SEARCH`}
      </button>

      {/* result message */}
      {result && (
        <div className={`text-[9px] font-data px-2 py-1 rounded border leading-snug ${
          result.success
            ? "text-hud-green bg-hud-green/10 border-hud-green/30"
            : "text-hud-red bg-hud-red/10 border-hud-red/30"
        }`}>
          {result.message}
        </div>
      )}
    </div>
  );
}
