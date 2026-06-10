export interface Reading {
  device_id: number;
  timestamp: number;
  temperature_c: number;
  humidity_pct: number;
}

interface ReadingsResponse { device_id: number; readings: Reading[]; }

const API_BASE = import.meta.env.VITE_API_URL ?? "";

export async function fetchReadings(
  deviceId: number,
  limit = 100
): Promise<Reading[]> {
  const url = `${API_BASE}/readings?device_id=${deviceId}&limit=${limit}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data: ReadingsResponse = await res.json();
  return data.readings;
}
