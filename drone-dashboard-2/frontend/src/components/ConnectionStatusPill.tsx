import { ConnectionStatus } from "../hooks/useTelemetry";

export default function ConnectionStatusPill({ status }: { status: ConnectionStatus }) {
  const map = {
    connected: { label: "LINK OK", cls: "bg-hud-green/10 border-hud-green text-hud-green" },
    connecting: { label: "CONNECTING…", cls: "bg-hud-amber/10 border-hud-amber text-hud-amber" },
    disconnected: { label: "NO LINK", cls: "bg-hud-red/10 border-hud-red text-hud-red" },
  } as const;
  const s = map[status];
  return (
    <div className={`font-data text-xs px-3 py-1 rounded-full border ${s.cls} flex items-center gap-2`}>
      <span className={`w-1.5 h-1.5 rounded-full ${status === "connected" ? "bg-hud-green" : status === "connecting" ? "bg-hud-amber" : "bg-hud-red"} animate-pulse`} />
      {s.label}
    </div>
  );
}
