import { useTelemetry } from "./hooks/useTelemetry";
import ArtificialHorizon from "./components/ArtificialHorizon";
import Compass from "./components/Compass";
import CameraFeed from "./components/CameraFeed";
import ArmedBadge from "./components/ArmedBadge";
import ModeIndicator from "./components/ModeIndicator";
import BatteryPanel from "./components/BatteryPanel";
import HeightGauge from "./components/HeightGauge";
import ConnectionStatusPill from "./components/ConnectionStatusPill";
import RecordingControls from "./components/RecordingControls";
import ImageUploader from "./components/ImageUploader";
import MatchGallery from "./components/MatchGallery";
import PositionReadout from "./components/PositionReadout";
import { getJetsonHost } from "./config";
import FlightTimer from "./components/FlightTimer";
import { useState, useRef, useCallback } from "react";
import FeatureSearchPanel from "./components/FeatureSearchPanel";

export default function App() {
  const { telemetry, status } = useTelemetry();
  const [dockingState, setDockingState] = useState<'idle' | 'waiting' | 'docking' | 'charging'>('idle');
  const containerRef = useRef<HTMLDivElement>(null);

  const handleFound = useCallback(() => {
    setTimeout(() => {
      if (containerRef.current) {
        containerRef.current.scrollTo({
          top: containerRef.current.scrollHeight,
          behavior: "smooth"
        });
      }
    }, 300);
  }, []);

  return (
    <div
      ref={containerRef}
      className="min-h-screen bg-hud-bg text-hud-text flex flex-col gap-3 p-3"
    >
      {/* header */}
      <header className="flex items-center justify-between px-1 shrink-0">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-bold tracking-widest font-data">DRONE GROUND STATION</h1>
          <span className="text-xs text-hud-dim font-data">{getJetsonHost()}</span>
        </div>
        <div className="flex items-center gap-3">
          <FlightTimer armed={telemetry.armed} />
          <ConnectionStatusPill status={status} />
        </div>
      </header>

      {/* main grid: camera (left) | instruments + uploader (right) */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-3 min-h-0 max-h-[620px]">
        <div className="lg:col-span-2 min-h-0">
          <CameraFeed status={status} />
        </div>

        {/* right column: horizon + compass row (small), then image uploader */}
        <div className="flex flex-col gap-3 min-h-0">
          {/* instruments row — horizon left, compass right, both compact */}
          <div className="grid grid-cols-2 gap-3" style={{ height: "200px" }}>
            <ArtificialHorizon roll={telemetry.roll} pitch={telemetry.pitch} />
            <Compass yaw={telemetry.yaw} />
          </div>

          {/* image upload panel */}
          <div className="flex-1 min-h-0">
            <ImageUploader />
          </div>
        </div>
      </div>

      {/* matched captures saved by the Jetson */}
      <div className="shrink-0">
        <MatchGallery />
      </div>

      {/* bottom status bar */}
      <div className="shrink-0 grid grid-cols-2 sm:grid-cols-6 gap-3 h-28">
        <ArmedBadge armed={telemetry.armed} />
        <ModeIndicator mode={telemetry.mode} />
        <BatteryPanel 
          voltage={telemetry.battery_voltage} 
          percent={telemetry.battery_percent} 
          armed={telemetry.armed}
          mode={telemetry.mode}
          lidarHeight={telemetry.lidar_height}
          onDockingStateChange={setDockingState}
        />
        <HeightGauge height={telemetry.lidar_height} />
        <PositionReadout />
        <RecordingControls lidarHeight={telemetry.lidar_height} />
      </div>

      <FeatureSearchPanel
        active={dockingState === 'charging'}
        onFound={handleFound}
      />
    </div>
  );
}

