interface Props {
  mode: string;
}

export default function ModeIndicator({ mode }: Props) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-hud-panelBorder bg-hud-panel px-4 py-3">
      <span className="text-[10px] tracking-widest text-hud-dim mb-1">FLIGHT MODE</span>
      <span className="text-xl font-bold font-data text-hud-text tracking-wide">{mode}</span>
    </div>
  );
}
