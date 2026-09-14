import { videoStreamUrl } from "../config";
import { ConnectionStatus } from "../hooks/useTelemetry";

interface Props {
  status: ConnectionStatus;
}

export default function CameraFeed({ status }: Props) {
  return (
    <div className="relative w-full h-full rounded-lg overflow-hidden border border-hud-panelBorder bg-black flex items-center justify-center">
      {status === "connected" ? (
        // eslint-disable-next-line jsx-a11y/alt-text
        <img
          src={videoStreamUrl()}
          className="w-full h-full object-contain"
          alt="Live camera feed"
        />
      ) : (
        <div className="text-hud-dim font-data text-sm flex flex-col items-center gap-2">
          <span className="text-3xl">⌁</span>
          <span>NO VIDEO SIGNAL</span>
        </div>
      )}
      <div className="absolute top-2 left-2 font-data text-xs bg-black/50 px-2 py-1 rounded text-hud-text/80">
        CAM01 · RGB
      </div>
    </div>
  );
}
