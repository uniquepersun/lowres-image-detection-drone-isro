import { useState } from "react";
import { useTelemetry } from "../hooks/useTelemetry";

export default function PositionReadout() {
  const { telemetry } = useTelemetry();
  const [tab, setTab] = useState<'local' | 'vo'>('local');

  const px = telemetry.pos_x || 0;
  const py = telemetry.pos_y || 0;
  const pz = telemetry.pos_z || 0;

  const vox = telemetry.vo_x || 0;
  const voy = telemetry.vo_y || 0;

  const isLocalTracking = px !== 0 || py !== 0 || pz !== 0;
  const isVoTracking = vox !== 0 || voy !== 0;

  return (
    <div className="flex flex-col h-full rounded-lg border border-hud-panelBorder bg-hud-panel overflow-hidden">
      {/* Tabs Header */}
      <div className="grid grid-cols-2 border-b border-hud-panelBorder/30 text-[9px] font-data tracking-wider uppercase text-center cursor-pointer select-none">
        <div
          onClick={() => setTab('local')}
          className={`py-1.5 transition-colors ${
            tab === 'local'
              ? "bg-black/30 text-hud-text border-r border-hud-panelBorder/30"
              : "text-hud-dim hover:text-hud-text hover:bg-black/10 border-r border-hud-panelBorder/30"
          }`}
        >
          LOCAL
        </div>
        <div
          onClick={() => setTab('vo')}
          className={`py-1.5 transition-colors ${
            tab === 'vo'
              ? "bg-black/30 text-hud-text"
              : "text-hud-dim hover:text-hud-text hover:bg-black/10"
          }`}
        >
          VISUAL ODOM
        </div>
      </div>

      <div className="flex-1 flex flex-col justify-center items-center gap-1 font-data px-2 py-1">
        {tab === 'local' ? (
          !isLocalTracking ? (
            <div className="text-hud-amber animate-pulse text-xs text-center leading-snug">
              WAITING FOR<br />LOCAL ODOM...
            </div>
          ) : (
            <div className="grid grid-cols-[16px_1fr] gap-x-2 w-full max-w-[120px] text-xs text-hud-text">
              <span className="text-hud-red text-right">X</span>
              <span>{px.toFixed(2)} m</span>

              <span className="text-hud-green text-right">Y</span>
              <span>{py.toFixed(2)} m</span>

              <span className="text-blue-400 text-right">Z</span>
              <span>{pz.toFixed(2)} m</span>
            </div>
          )
        ) : (
          !isVoTracking ? (
            <div className="text-hud-amber animate-pulse text-xs text-center leading-snug">
              WAITING FOR<br />VISUAL ODOM...
            </div>
          ) : (
            <div className="grid grid-cols-[16px_1fr] gap-x-2 w-full max-w-[100px] text-xs text-hud-text">
              <span className="text-hud-red text-right font-bold">X</span>
              <span>{vox.toFixed(4)}</span>

              <span className="text-hud-green text-right font-bold">Y</span>
              <span>{voy.toFixed(4)}</span>
            </div>
          )
        )}
      </div>
    </div>
  );
}
