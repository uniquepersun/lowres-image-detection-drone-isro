import { useEffect, useRef } from "react";

interface Props {
  roll: number;  // degrees
  pitch: number; // degrees
}

const PITCH_PX_PER_DEG = 6;

export default function ArtificialHorizon({ roll, pitch }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const w = rect.width;
    const h = rect.height;
    const cx = w / 2;
    const cy = h / 2;

    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, w, h);
    ctx.clip();

    // rotate + translate for roll/pitch
    ctx.translate(cx, cy);
    ctx.rotate((-roll * Math.PI) / 180);
    const pitchOffset = pitch * PITCH_PX_PER_DEG;

    const span = Math.max(w, h) * 2;

    // sky
    const skyGrad = ctx.createLinearGradient(0, -span, 0, 0);
    skyGrad.addColorStop(0, "#1b3a5c");
    skyGrad.addColorStop(1, "#3a6ea5");
    ctx.fillStyle = skyGrad;
    ctx.fillRect(-span, -span + pitchOffset, span * 2, span);

    // ground
    const groundGrad = ctx.createLinearGradient(0, 0, 0, span);
    groundGrad.addColorStop(0, "#5b3f25");
    groundGrad.addColorStop(1, "#2e2013");
    ctx.fillStyle = groundGrad;
    ctx.fillRect(-span, pitchOffset, span * 2, span);

    // horizon line
    ctx.strokeStyle = "#e2e8f0";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(-span, pitchOffset);
    ctx.lineTo(span, pitchOffset);
    ctx.stroke();

    // pitch ladder
    ctx.strokeStyle = "rgba(226,232,240,0.85)";
    ctx.fillStyle = "rgba(226,232,240,0.85)";
    ctx.font = "11px JetBrains Mono, monospace";
    ctx.lineWidth = 1.5;
    for (let p = -90; p <= 90; p += 10) {
      if (p === 0) continue;
      const y = pitchOffset - p * PITCH_PX_PER_DEG;
      if (Math.abs(y) > span) continue;
      const lineWidth = p % 30 === 0 ? 50 : 28;
      ctx.beginPath();
      ctx.moveTo(-lineWidth, y);
      ctx.lineTo(lineWidth, y);
      ctx.stroke();
      if (p % 30 === 0) {
        ctx.save();
        ctx.translate(-lineWidth - 22, y);
        ctx.rotate((roll * Math.PI) / 180); // keep numbers upright
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(p), 0, 0);
        ctx.restore();
      }
    }

    ctx.restore();

    // fixed aircraft symbol (does not rotate with roll)
    ctx.strokeStyle = "#facc15";
    ctx.fillStyle = "#facc15";
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(cx - 40, cy);
    ctx.lineTo(cx - 12, cy);
    ctx.lineTo(cx - 6, cy + 8);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + 40, cy);
    ctx.lineTo(cx + 12, cy);
    ctx.lineTo(cx + 6, cy + 8);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fill();

    // roll indicator arc at top
    ctx.strokeStyle = "#e2e8f0";
    ctx.lineWidth = 1.5;
    const arcR = Math.min(w, h) * 0.42;
    ctx.beginPath();
    ctx.arc(cx, cy, arcR, (210 * Math.PI) / 180, (330 * Math.PI) / 180);
    ctx.stroke();
    [-60, -45, -30, -15, 0, 15, 30, 45, 60].forEach((deg) => {
      const a = ((deg - 90) * Math.PI) / 180;
      const inner = deg === 0 ? arcR - 10 : arcR - 6;
      const x1 = cx + inner * Math.cos(a);
      const y1 = cy + inner * Math.sin(a);
      const x2 = cx + arcR * Math.cos(a);
      const y2 = cy + arcR * Math.sin(a);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    });
    // roll pointer triangle, rotates with roll
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate((roll * Math.PI) / 180);
    ctx.fillStyle = "#facc15";
    ctx.beginPath();
    ctx.moveTo(0, -arcR + 2);
    ctx.lineTo(-6, -arcR + 14);
    ctx.lineTo(6, -arcR + 14);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }, [roll, pitch]);

  return (
    <div className="relative w-full h-full rounded-lg overflow-hidden border border-hud-panelBorder bg-black">
      <canvas ref={canvasRef} className="w-full h-full block" />
      <div className="absolute top-2 left-2 font-data text-xs text-hud-text/80 bg-black/40 px-2 py-1 rounded">
        ROLL {roll >= 0 ? "+" : ""}
        {roll.toFixed(1)}°
      </div>
      <div className="absolute top-2 right-2 font-data text-xs text-hud-text/80 bg-black/40 px-2 py-1 rounded">
        PITCH {pitch >= 0 ? "+" : ""}
        {pitch.toFixed(1)}°
      </div>
    </div>
  );
}
