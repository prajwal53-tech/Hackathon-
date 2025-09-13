import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { EventSourcePolyfill } from 'eventsource-polyfill'

type Stop = { id: string; name: string; lat: number; lon: number }
type Route = { id: string; name: string; stops: string[] }
type Bus = { id: string; route_id: string; lat: number; lon: number; next_stop_id?: string; eta_next_stop_s?: number }
type Schedule = { route_id: string; stop_id: string; planned_time: number; optimized_time?: number }

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

function App() {
  const [stops, setStops] = useState<Stop[]>([])
  const [routes, setRoutes] = useState<Route[]>([])
  const [schedule, setSchedule] = useState<Schedule[]>([])
  const [buses, setBuses] = useState<Bus[]>([])
  const [alerts, setAlerts] = useState<string[]>([])
  const [ridershipSeries, setRidershipSeries] = useState<{ ts: number; count: number; forecast?: number }[]>([])
  const sseRef = useRef<EventSource | null>(null)

  useEffect(() => {
    ;(async () => {
      const res = await axios.get(`${API_BASE}/static`)
      setStops(res.data.stops)
      setRoutes(res.data.routes)
      setSchedule(res.data.schedule)
    })()
  }, [])

  useEffect(() => {
    const es = new EventSourcePolyfill(`${API_BASE}/sse`, { heartbeatTimeout: 30_000 })
    sseRef.current = es as unknown as EventSource
    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'buses') {
          setBuses(msg.data.buses)
        } else if (msg.type === 'ticket') {
          setRidershipSeries((prev) => {
            const next = [...prev, { ts: msg.data.ts * 1000, count: msg.data.count }]
            return next.slice(-120)
          })
        } else if (msg.type === 'schedule_opt') {
          setAlerts((prev) => [`Rescheduling at ${new Date(msg.data.ts * 1000).toLocaleTimeString()}`, ...prev].slice(0, 5))
          setRidershipSeries((prev) => {
            if (prev.length === 0) return prev
            const lastTs = prev[prev.length - 1].ts
            const next = [...prev]
            next[next.length - 1] = { ...prev[prev.length - 1], forecast: msg.data.avg_forecast }
            return next
          })
          // Refresh schedule snapshot to reflect optimized times
          axios.get(`${API_BASE}/static`).then((res) => setSchedule(res.data.schedule)).catch(() => {})
        }
      } catch (e) {
        // ignore
      }
    }
    es.onerror = () => {
      setAlerts((prev) => ["SSE connection lost. Reconnecting...", ...prev].slice(0, 5))
    }
    return () => {
      es.close()
    }
  }, [])

  const center = useMemo(() => {
    if (stops.length > 0) {
      return [stops[0].lat, stops[0].lon] as [number, number]
    }
    return [37.7749, -122.4194] as [number, number]
  }, [stops])

  return (
    <div className="App">
      <h1>Smart Bus Optimization</h1>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={{ height: 400 }}>
          <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%' }}>
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap" />
            {stops.map((s) => (
              <Marker key={s.id} position={[s.lat, s.lon]}>
                <Popup>{s.name}</Popup>
              </Marker>
            ))}
            {buses.map((b) => (
              <Marker key={b.id} position={[b.lat, b.lon]}>
                <Popup>
                  Bus {b.id} on {b.route_id}
                  <br /> Next: {b.next_stop_id} ETA: {b.eta_next_stop_s}s
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>

        <div style={{ height: 400, padding: 8 }}>
          <h3>Ridership (recent)</h3>
          <ResponsiveContainer width="100%" height="90%">
            <LineChart data={ridershipSeries} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="ts" tickFormatter={(v) => new Date(v).toLocaleTimeString()} type="number" domain={['auto', 'auto']} />
              <YAxis />
              <Tooltip labelFormatter={(v) => new Date(v as number).toLocaleTimeString()} />
              <Line type="monotone" dataKey="count" name="Actual" stroke="#8884d8" dot={false} />
              <Line type="monotone" dataKey="forecast" name="Forecast" stroke="#ff7300" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div style={{ gridColumn: '1 / span 2', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div style={{ maxHeight: 260, overflowY: 'auto', padding: 8, border: '1px solid #ccc' }}>
            <h3>Alerts</h3>
            <ul>
              {alerts.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
          <div style={{ maxHeight: 260, overflowY: 'auto', padding: 8, border: '1px solid #ccc' }}>
            <h3>Schedules (sample)</h3>
            <table style={{ width: '100%', fontSize: 12 }}>
              <thead>
                <tr>
                  <th>Route</th>
                  <th>Stop</th>
                  <th>Planned</th>
                  <th>Optimized</th>
                </tr>
              </thead>
              <tbody>
                {schedule.slice(0, 50).map((s, i) => (
                  <tr key={i}>
                    <td>{s.route_id}</td>
                    <td>{s.stop_id}</td>
                    <td>{new Date(s.planned_time * 1000).toLocaleTimeString()}</td>
                    <td>{s.optimized_time ? new Date(s.optimized_time * 1000).toLocaleTimeString() : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
