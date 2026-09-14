export interface Telemetry {
  armed: boolean;
  mode: string;
  battery_voltage: number;
  battery_percent: number;
  roll: number;
  pitch: number;
  yaw: number;
  lidar_height: number;
  pos_x: number;
  pos_y: number;
  pos_z: number;
  vo_x?: number;
  vo_y?: number;
  timestamp: number;
}

export const DEFAULT_TELEMETRY: Telemetry = {
  armed: false,
  mode: "UNKNOWN",
  battery_voltage: 0,
  battery_percent: 0,
  roll: 0,
  pitch: 0,
  yaw: 0,
  lidar_height: 0,
  pos_x: 0,
  pos_y: 0,
  pos_z: 0,
  vo_x: 0,
  vo_y: 0,
  timestamp: 0,
};

// Change these to match your Jetson's IP address on the local network.
// Easiest: set window.localStorage.setItem("JETSON_HOST", "192.168.1.50")
// from the browser console, or just edit the default below.
const DEFAULT_HOST = "car@car.local";
const DEFAULT_PORT = 8000;

export function getJetsonHost(): string {
  return localStorage.getItem("JETSON_HOST") || DEFAULT_HOST;
}

export function getJetsonPort(): number {
  const p = localStorage.getItem("JETSON_PORT");
  return p ? parseInt(p, 10) : DEFAULT_PORT;
}

export function telemetryWsUrl(): string {
  const host = getJetsonHost();
  const cleanHost = host.includes("@") ? host.split("@")[1] : host;
  return `ws://${cleanHost}:${getJetsonPort()}/telemetry`;
}

export function videoStreamUrl(): string {
  const host = getJetsonHost();
  const cleanHost = host.includes("@") ? host.split("@")[1] : host;
  return `http://${cleanHost}:${getJetsonPort()}/video`;
}
