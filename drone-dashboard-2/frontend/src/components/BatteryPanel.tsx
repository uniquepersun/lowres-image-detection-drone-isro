import { useEffect, useState } from "react";

interface Props {
  voltage: number;
  percent: number;
  armed: boolean;
  mode: string;
  lidarHeight: number;
  onDockingStateChange?: (state: 'idle' | 'waiting' | 'docking' | 'charging') => void;
}

function colorFor(percent: number) {
  if (percent > 50) return { text: "text-hud-green", bg: "bg-hud-green", border: "border-hud-green" };
  if (percent > 25) return { text: "text-hud-amber", bg: "bg-hud-amber", border: "border-hud-amber" };
  return { text: "text-hud-red", bg: "bg-hud-red", border: "border-hud-red" };
}

export default function BatteryPanel({ voltage, percent, armed, mode, lidarHeight, onDockingStateChange }: Props) {
  const [dockingState, setDockingState] = useState<'idle' | 'waiting' | 'docking' | 'charging'>('idle');
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    onDockingStateChange?.(dockingState);
  }, [dockingState, onDockingStateChange]);

  useEffect(() => {
    // Start docking sequence if conditions are met
    if (!armed && mode === "LAND" && lidarHeight < 0.15) {
      if (dockingState === 'idle') {
        setDockingState('waiting');
      }
    } else if (armed) {
      // Abort docking/charging if armed again
      setDockingState('idle');
      setProgress(0);
    }
  }, [armed, mode, lidarHeight, dockingState]);

  useEffect(() => {
    if (dockingState === 'waiting') {
      const timer = setTimeout(() => {
        setDockingState('docking');
        setProgress(0);
      }, 8000);
      return () => clearTimeout(timer);
    }
  }, [dockingState]);

  useEffect(() => {
    if (dockingState === 'docking') {
      fetch("http://10.86.127.107/motor_off", { mode: "no-cors" }).catch((err) => {
        console.error("Failed to trigger ESP motor_on:", err);
      });
    } else if (dockingState === 'charging') {
      fetch("http://10.86.127.107/charge_on", { mode: "no-cors" }).catch((err) => {
        console.error("Failed to trigger ESP charging_on:", err);
      });
    }
  }, [dockingState]);

  useEffect(() => {
    if (dockingState === 'docking') {
      const duration = 20000; // 20s
      const startTime = Date.now();
      
      const interval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        if (elapsed >= duration) {
          setProgress(100);
          setDockingState('charging');
          clearInterval(interval);
        } else {
          setProgress((elapsed / duration) * 100);
        }
      }, 100);
      
      return () => clearInterval(interval);
    }
  }, [dockingState]);

  const c = colorFor(percent);
  const clamped = Math.max(0, Math.min(100, percent));

  if (dockingState === 'docking') {
    return (
      <div className={`flex flex-col justify-center rounded-lg border border-hud-amber/40 bg-hud-panel px-4 py-3 gap-2`}>
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] tracking-widest text-hud-dim">BASE STATION</span>
          <span className="font-data text-[10px] text-hud-amber animate-pulse">DOCKING...</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 rounded-full bg-black/40 overflow-hidden">
            <div className={`h-full bg-hud-amber`} style={{ width: `${progress}%` }} />
          </div>
          <span className={`font-data text-xs text-hud-amber w-8 text-right`}>
            {progress.toFixed(0)}%
          </span>
        </div>
      </div>
    );
  }

  if (dockingState === 'charging') {
    return (
      <div className={`flex flex-col justify-center rounded-lg border border-hud-green/40 bg-hud-panel px-4 py-3 gap-2`}>
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] tracking-widest text-hud-green animate-pulse">CHARGING STARTED</span>
          <span className={`font-data text-sm text-hud-green`}>{voltage.toFixed(1)}V</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 rounded-full bg-black/40 overflow-hidden">
            <div className={`h-full bg-hud-green animate-pulse`} style={{ width: `${clamped}%` }} />
          </div>
          <span className={`font-data text-lg font-bold text-hud-green w-14 text-right`}>
            {percent.toFixed(0)}%
          </span>
        </div>
      </div>
    );
  }

  // default idle state — voltage hidden until backend reports a valid pack voltage
  return (
    <div className={`flex flex-col justify-center rounded-lg border ${c.border}/40 bg-hud-panel px-4 py-3 gap-2`}>
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] tracking-widest text-hud-dim">BATTERY</span>
        <span className={`font-data text-lg font-bold ${c.text} w-14 text-right`}>
          {percent.toFixed(0)}%
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-2 rounded-full bg-black/40 overflow-hidden">
          <div className={`h-full ${c.bg}`} style={{ width: `${clamped}%` }} />
        </div>
      </div>
    </div>
  );
}
