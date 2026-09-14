interface Props {
  armed: boolean;
}

export default function ArmedBadge({ armed }: Props) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-lg border px-4 py-3 font-data ${
        armed
          ? "bg-hud-green/10 border-hud-green text-hud-green"
          : "bg-hud-red/10 border-hud-red text-hud-red"
      }`}
    >
      <span className="text-[10px] tracking-widest text-hud-dim mb-1">STATUS</span>
      <span className="text-xl font-bold tracking-wide">{armed ? "ARMED" : "DISARMED"}</span>
    </div>
  );
}
