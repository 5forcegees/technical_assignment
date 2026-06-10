import { useState, useEffect, useCallback } from "react";
import { fetchReadings, type Reading } from "./api";

const POLL_INTERVAL_MS = 60_000;

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export default function App() {
  const [deviceId, setDeviceId] = useState<number>(1);
  const [inputId, setInputId]   = useState<string>("1");
  const [readings, setReadings] = useState<Reading[]>([]);
  const [error, setError]       = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);

  const load = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchReadings(id, 100);
      setReadings(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(deviceId);
    const timer = setInterval(() => load(deviceId), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [deviceId, load]);

  const latest = readings.at(-1);

  return (
    <div style={{ fontFamily: "monospace", maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <h1>Weather Station Monitor</h1>

      <div style={{ marginBottom: 16 }}>
        <label htmlFor="device-input">Device ID:&nbsp;</label>
        <input
          id="device-input"
          type="number"
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          style={{ width: 80 }}
        />
        <button
          onClick={() => {
            const n = parseInt(inputId, 10);
            if (!isNaN(n)) setDeviceId(n);
          }}
          style={{ marginLeft: 8 }}
        >
          Load
        </button>
        {loading && <span style={{ marginLeft: 12, color: "gray" }}>Loading…</span>}
      </div>

      {error && (
        <p style={{ color: "red" }}>Error: {error}</p>
      )}

      {latest && (
        <div style={{ border: "1px solid #ccc", padding: 16, marginBottom: 24 }}>
          <h2 style={{ marginTop: 0 }}>Latest — Device {latest.device_id}</h2>
          <p><strong>Temperature:</strong> {latest.temperature_c} °C</p>
          <p><strong>Humidity:</strong>    {latest.humidity_pct} %</p>
          <p><strong>Time:</strong>        {formatTs(latest.timestamp)}</p>
        </div>
      )}

      {readings.length > 0 && (
        <>
          <h2>Last {readings.length} readings</h2>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #333" }}>
                <th style={{ textAlign: "left", padding: "4px 8px" }}>Time</th>
                <th style={{ textAlign: "right", padding: "4px 8px" }}>Temp (°C)</th>
                <th style={{ textAlign: "right", padding: "4px 8px" }}>Humidity (%)</th>
              </tr>
            </thead>
            <tbody>
              {readings.map((r) => (
                <tr key={r.timestamp} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "4px 8px" }}>{formatTs(r.timestamp)}</td>
                  <td style={{ textAlign: "right", padding: "4px 8px" }}>
                    {r.temperature_c}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 8px" }}>
                    {r.humidity_pct}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {!loading && readings.length === 0 && !error && (
        <p style={{ color: "gray" }}>No readings found for device {deviceId}.</p>
      )}
    </div>
  );
}
