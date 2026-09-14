import { useState, useEffect, useRef } from "react";

interface Props {
  armed: boolean;
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function FlightTimer({ armed }: Props) {
  const [elapsed, setElapsed] = useState(0);       // total accumulated seconds
  const [hovered, setHovered] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const armedRef = useRef(armed);

  // Tick every second when armed
  useEffect(() => {
    armedRef.current = armed;
    if (armed) {
      intervalRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [armed]);

  const reset = () => setElapsed(0);

  const isRunning = armed;
  const hasTime = elapsed > 0;

  return (
    <div
      className="relative flex items-center gap-2"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Timer display */}
      <div
        className={`flex items-center gap-1.5 px-3 py-1 rounded border font-data text-sm tracking-widest transition-all ${
          isRunning
            ? "border-hud-green/60 bg-hud-green/10 text-hud-green"
            : hasTime
            ? "border-hud-amber/40 bg-hud-amber/5 text-hud-amber"
            : "border-hud-panelBorder/50 bg-transparent text-hud-dim"
        }`}
      >
        {/* indicator dot */}
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            isRunning ? "bg-hud-green animate-pulse" : hasTime ? "bg-hud-amber" : "bg-hud-dim/40"
          }`}
        />
        <span>{formatTime(elapsed)}</span>
        {/* status label */}
        <span className="text-[9px] opacity-60 ml-0.5">
          {isRunning ? "FLT" : hasTime ? "PAUSED" : "IDLE"}
        </span>
      </div>

      {/* Reset button — appears on hover if there's accumulated time */}
      {hovered && hasTime && (
        <button
          onClick={reset}
          title="Reset timer"
          className="absolute -right-7 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full border border-hud-red/60 bg-hud-red/10 hover:bg-hud-red/25 text-hud-red text-[10px] flex items-center justify-center transition-all"
        >
          ↺
        </button>
      )}
    </div>
  );
}
