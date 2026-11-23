// The most recent sensor readings from all devices, newest at the top.
export default function TelemetryTable({ readings }) {
  return (
    <section className="panel">
      <h2>Live telemetry</h2>
      {readings.length === 0 ? (
        <p className="muted">No readings yet. Start the simulation.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Device</th>
                <th>Temp</th>
                <th>Humidity</th>
                <th>Battery</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {readings.map((r) => (
                <tr key={r.id}>
                  <td>{new Date(r.timestamp).toLocaleTimeString()}</td>
                  <td>{r.device_id}</td>
                  <td>{r.temperature.toFixed(1)}°C</td>
                  <td>{r.humidity.toFixed(1)}%</td>
                  <td>{r.battery.toFixed(0)}%</td>
                  <td className="muted">{r.source.replace("/", " via ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
