import { useState, useEffect, useRef } from "react";
import { videoStreamUrl } from "../config";

interface RecordingStatus {
  recording: boolean;
  frame_count: number;
}

interface RecordingControlsProps {
  lidarHeight: number;
}

export default function RecordingControls({ lidarHeight }: RecordingControlsProps) {
  const [status, setStatus] = useState<RecordingStatus>({
    recording: false,
    frame_count: 0,
  });
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [storeProgress, setStoreProgress] = useState<{
    stage: "idle" | "downloading" | "storing" | "completed" | "error";
    percent: number;
    message?: string;
  }>({ stage: "idle", percent: 0 });

  const autoStarted = useRef(false);

  const rawBase = videoStreamUrl().split("/video")[0];
  let base = rawBase;
  try {
    const url = new URL(rawBase);
    url.username = "";
    url.password = "";
    base = url.toString().replace(/\/$/, "");
  } catch (e) {
    console.error("Failed to clean base URL:", e);
  }

  // Poll recording status from backend
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${base}/recording/status`);
        if (res.ok) {
          setStatus(await res.json());
          setError(null);
        }
      } catch (e) {
        setError(`Status check failed: ${e}`);
      }
    }, 500);
    return () => clearInterval(interval);
  }, [base]);

  // Automatic capture logic based on rangefinder height
  useEffect(() => {
    // Height goes above 1.0m -> Start Recording
    if (!status.recording && storeProgress.stage === "idle" && lidarHeight > 1.0 && !autoStarted.current) {
      autoStarted.current = true;
      startRecording();
    }
    // Height goes below 0.5m -> Stop and save to Mac
    if (status.recording && autoStarted.current && lidarHeight < 0.5) {
      autoStarted.current = false;
      stopAndSaveFlow();
    }
  }, [lidarHeight, status.recording, storeProgress.stage]);

  const startRecording = async () => {
    try {
      const res = await fetch(`${base}/recording/start`, { method: "POST" });
      if (res.ok) {
        setError(null);
      } else {
        setError("Failed to start recording");
        autoStarted.current = false;
      }
    } catch (e) {
      setError(`Error: ${e}`);
      autoStarted.current = false;
    }
  };

  const stopRecording = async (): Promise<boolean> => {
    try {
      const res = await fetch(`${base}/recording/stop`, { method: "POST" });
      if (res.ok) {
        setError(null);
        return true;
      } else {
        setError("Failed to stop recording");
        return false;
      }
    } catch (e) {
      setError(`Error: ${e}`);
      return false;
    }
  };

  const stopAndSaveFlow = async () => {
    try {
      setError(null);
      setStoreProgress({ stage: "downloading", percent: 0 });

      // Stop recording
      const stopped = await stopRecording();
      if (!stopped) {
        throw new Error("Could not stop recording on drone");
      }

      // Fetch the last status to get final frame count
      const statusRes = await fetch(`${base}/recording/status`);
      let count = status.frame_count;
      if (statusRes.ok) {
        const currentStatus = await statusRes.json();
        count = currentStatus.frame_count;
        setStatus(currentStatus);
      }

      if (count === 0) {
        throw new Error("No frames recorded to save");
      }

      // Start downloading with progress tracking
      const res = await fetch(`${base}/recording/download`);
      if (!res.ok) {
        throw new Error("Download from drone failed");
      }

      const contentLength = res.headers.get("Content-Length");
      const totalBytes = contentLength ? parseInt(contentLength, 10) : 0;
      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error("Could not read response stream");
      }

      let receivedBytes = 0;
      const chunks: Uint8Array[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        receivedBytes += value.length;
        if (totalBytes > 0) {
          const percent = Math.round((receivedBytes / totalBytes) * 100);
          setStoreProgress({ stage: "downloading", percent });
        }
      }

      const blob = new Blob(chunks as BlobPart[], { type: "application/zip" });

      // Upload to local Vite server on Mac
      setStoreProgress({ stage: "storing", percent: 0 });

      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/save-zip");
      xhr.setRequestHeader("Content-Type", "application/zip");

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          setStoreProgress({ stage: "storing", percent: Math.round(percent * 0.9) });
        }
      };

      const uploadPromise = new Promise<{ success: boolean; path: string; fileCount: number }>((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status === 200) {
            try {
              resolve(JSON.parse(xhr.responseText));
            } catch {
              reject(new Error("Invalid response from local server"));
            }
          } else {
            try {
              const errData = JSON.parse(xhr.responseText);
              reject(new Error(`Server error: ${errData.error || errData.details || xhr.statusText}`));
            } catch {
              reject(new Error(`Vite server responded with: ${xhr.statusText}`));
            }
          }
        };
        xhr.onerror = () => reject(new Error("Failed to connect to local Vite server"));
      });

      xhr.send(blob);

      const result = await uploadPromise;

      setStoreProgress({
        stage: "completed",
        percent: 100,
        message: `Captured ${result.fileCount} flight`
      });

      // Clear after a delay
      setTimeout(() => {
        setStoreProgress({ stage: "idle", percent: 0 });
      }, 5000);

    } catch (e: any) {
      console.error(e);
      setError(`Auto-save failed: ${e.message}`);
      setStoreProgress({ stage: "error", percent: 0, message: e.message });
      setTimeout(() => {
        setStoreProgress({ stage: "idle", percent: 0 });
      }, 5000);
    }
  };

  const downloadRecording = async () => {
    setDownloading(true);
    try {
      const res = await fetch(`${base}/recording/download`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "drone_frames.zip";
        a.click();
        URL.revokeObjectURL(url);
        setError(null);
      } else {
        const data = await res.json();
        setError(data.error || "Download failed");
      }
    } catch (e) {
      setError(`Download error: ${e}`);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="bg-hud-panel border border-hud-panelBorder rounded-lg p-4 flex flex-col gap-3">
      <div className="text-[10px] tracking-widest text-hud-dim">FRAME RECORDING</div>

      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-data text-hud-text">
            {status.recording ? "🔴 RECORDING" : "⚫ IDLE"}
          </span>
          <span className="text-xs font-data text-hud-dim">{status.frame_count} frames</span>
        </div>
        {autoStarted.current && (
          <span className="text-[9px] font-data bg-hud-amber/10 border border-hud-amber/30 text-hud-amber px-1.5 py-0.5 rounded animate-pulse">
            🤖 AUTO
          </span>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={startRecording}
          disabled={status.recording}
          className={`px-3 py-1.5 text-xs font-data rounded border transition ${
            status.recording
              ? "bg-hud-green/20 border-hud-green/50 text-hud-dim cursor-not-allowed"
              : "bg-hud-green/10 border-hud-green text-hud-green hover:bg-hud-green/20"
          }`}
        >
          START
        </button>
        <button
          onClick={async () => {
            autoStarted.current = false;
            await stopRecording();
          }}
          disabled={!status.recording}
          className={`px-3 py-1.5 text-xs font-data rounded border transition ${
            !status.recording
              ? "bg-hud-red/20 border-hud-red/50 text-hud-dim cursor-not-allowed"
              : "bg-hud-red/10 border-hud-red text-hud-red hover:bg-hud-red/20"
          }`}
        >
          STOP
        </button>
      </div>

      {status.frame_count > 0 && (
        <button
          onClick={downloadRecording}
          disabled={downloading || status.recording}
          className={`px-3 py-1.5 text-xs font-data rounded border transition ${
            downloading || status.recording
              ? "bg-hud-amber/20 border-hud-amber/50 text-hud-dim cursor-not-allowed"
              : "bg-hud-amber/10 border-hud-amber text-hud-amber hover:bg-hud-amber/20"
          }`}
        >
          {downloading ? "DOWNLOADING..." : `DOWNLOAD (${status.frame_count})`}
        </button>
      )}

      {storeProgress.stage !== "idle" && (
        <div className="flex flex-col gap-1.5 mt-1 p-2 bg-black/30 border border-hud-panelBorder rounded">
          <div className="flex justify-between text-[9px] font-data">
            <span className="text-hud-dim uppercase">
              {storeProgress.stage === "downloading" && "📥 Downloading zip..."}
              {storeProgress.stage === "storing" && "💾 Storing to Mac..."}
              {storeProgress.stage === "completed" && "✅ Saved successfully"}
              {storeProgress.stage === "error" && "❌ Save failed"}
            </span>
            <span className={storeProgress.stage === "completed" ? "text-hud-green" : "text-hud-dim"}>
              {storeProgress.percent}%
            </span>
          </div>
          <div className="h-1.5 w-full bg-hud-panelBorder/30 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 rounded-full ${
                storeProgress.stage === "completed"
                  ? "bg-hud-green"
                  : storeProgress.stage === "error"
                  ? "bg-hud-red"
                  : "bg-hud-amber animate-pulse"
              }`}
              style={{ width: `${storeProgress.percent}%` }}
            />
          </div>
          {storeProgress.message && (
            <div className="text-[9px] font-data text-hud-dim mt-0.5 leading-tight">
              {storeProgress.message}
            </div>
          )}
        </div>
      )}

      {error && <div className="text-xs text-hud-red bg-hud-red/10 border border-hud-red/30 rounded px-2 py-1 leading-snug break-all">{error}</div>}
    </div>
  );
}
