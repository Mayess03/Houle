
const API_URL = "/api";

export interface Stats {
  total_buoys: number;
  online_buoys: number;
  silent_buoys: number;
  buoys_with_low_battery: number;
  buoys_with_high_waves: number;
  total_active_alerts: number;
}

export interface Measurement {
  measurement_id: string;
  buoy_id: string;
  measured_at: string;
  received_at: string;
  wave_height: number;
  battery_level: number;
  latitude: number;
  longitude: number;
}

export interface Buoy {
  buoy_id: string;
  status: string;
  last_seen_at: string;
  latest_measurement: Measurement;
  alerts: string[];
}

export interface Alert {
  buoy_id: string;
  type: string;
  severity: string;
  message: string;
  value: number;
  threshold: number;
}

async function request<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_URL}${endpoint}`);

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

export const getStats = () => request<Stats>("/stats");

export const getBuoys = () => request<Buoy[]>("/buoys");

export const getAlerts = () => request<Alert[]>("/alerts");

export const getBuoyHistory = (id: string) =>
  request<Measurement[]>(`/buoys/${encodeURIComponent(id)}/history`);
