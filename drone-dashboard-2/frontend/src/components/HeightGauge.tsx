interface Props {
  height: number; // meters
}

// visible tape window, in meters above/below current height
const WINDOW = 3;
const TICK_STEP = 0.5;

export default function HeightGauge({ height }: Props) {
  const ticks = [];
  const start = Math.floor((height - WINDOW) / TICK_STEP) * TICK_STEP;
  for (let v = start; v <= height + WINDOW; v += TICK_STEP) {
    ticks.push(Math.round(v * 10) / 10);
  }

  return (
    <div className="flex flex-col h-full rounded-lg border border-hud-panelBorder bg-hud-panel overflow-hidden">
      <div className="text-[10px] tracking-widest text-hud-dim text-center pt-2">HEIGHT (LIDAR)</div>
      <div className="relative flex-1 flex items-center justify-center">
        <div className="relative h-full w-20 overflow-hidden">
          {ticks.map((v) => {
            const offsetM = v - height;
            const pct = 50 - (offsetM / WINDOW) * 50; // top=0%, bottom=100%
            if (pct < -10 || pct > 110) return null;
            const isMajor = Math.abs(v % 1) < 0.001;
            return (
              <div
                key={v}
                className="absolute left-0 w-full flex items-center"
                style={{ top: `${pct}%` }}
              >
                <div className={`h-px bg-hud-dim ${isMajor ? "w-5" : "w-3"}`} />
                {isMajor && (
                  <span className="ml-1 font-data text-[10px] text-hud-dim">{v.toFixed(0)}</span>
                )}
              </div>
            );
          })}
          {/* center indicator */}
          <div className="absolute left-0 top-1/2 -translate-y-1/2 w-full h-7 bg-black/50 border-y border-hud-green flex items-center justify-center">
            <span className="font-data text-sm font-bold text-hud-green">{height.toFixed(2)}</span>
          </div>
        </div>
      </div>
      <div className="text-center pb-2 font-data text-2xl font-bold text-hud-text">
        {height.toFixed(2)}<span className="text-sm text-hud-dim ml-1">m</span>
      </div>
    </div>
  );
}
