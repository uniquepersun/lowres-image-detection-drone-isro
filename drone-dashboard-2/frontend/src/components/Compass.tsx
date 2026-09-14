interface Props {
  yaw: number; // 0-360
}

const TICKS = Array.from({ length: 36 }, (_, i) => i * 10);
const LABELS: Record<number, string> = { 0: "N", 90: "E", 180: "S", 270: "W" };

export default function Compass({ yaw }: Props) {
  const size = 220;
  const r = 92;
  const cx = size / 2;
  const cy = size / 2;

  return (
    <div className="relative w-full h-full flex items-center justify-center rounded-lg border border-hud-panelBorder bg-hud-panel overflow-hidden p-2">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="w-full h-full"
        preserveAspectRatio="xMidYMid meet"
      >
        <g transform={`rotate(${-yaw} ${cx} ${cy})`}>
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1f2937" strokeWidth="2" />
          {TICKS.map((deg) => {
            const a = (deg * Math.PI) / 180;
            const isCardinal = deg % 90 === 0;
            const isMajor = deg % 30 === 0;
            const len = isCardinal ? 16 : isMajor ? 11 : 6;
            const x1 = cx + (r - len) * Math.sin(a);
            const y1 = cy - (r - len) * Math.cos(a);
            const x2 = cx + r * Math.sin(a);
            const y2 = cy - r * Math.cos(a);
            return (
              <line
                key={deg}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={isCardinal ? "#facc15" : "#64748b"}
                strokeWidth={isCardinal ? 2.5 : 1.5}
              />
            );
          })}
          {Object.entries(LABELS).map(([deg, label]) => {
            const a = (parseInt(deg) * Math.PI) / 180;
            const lx = cx + (r - 30) * Math.sin(a);
            const ly = cy - (r - 30) * Math.cos(a);
            return (
              <text
                key={deg}
                x={lx}
                y={ly}
                fill="#facc15"
                fontSize="16"
                fontWeight="700"
                textAnchor="middle"
                dominantBaseline="middle"
                transform={`rotate(${yaw} ${lx} ${ly})`}
              >
                {label}
              </text>
            );
          })}
        </g>

        {/* fixed heading pointer */}
        <polygon
          points={`${cx},${cy - r - 4} ${cx - 6},${cy - r + 10} ${cx + 6},${cy - r + 10}`}
          fill="#ef4444"
        />
      </svg>

      <div className="absolute bottom-3 font-data text-lg font-semibold text-hud-text bg-black/40 px-3 py-0.5 rounded">
        {yaw.toFixed(0).padStart(3, "0")}°
      </div>
    </div>
  );
}
