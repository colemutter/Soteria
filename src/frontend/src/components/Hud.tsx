import { useEffect, useState } from 'react'
import { simClock } from '../lib/simClock'
import { geodeticAt, orbitalElements, type GeodeticInfo } from '../lib/orbital'
import type { SatelliteEntry } from '../data/satellites'
import { DangerIcon, DANGER_LABELS } from './DangerIcon'

interface Props {
  satellites: SatelliteEntry[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  shadingOn: boolean
  onToggleShading: () => void
  solarWindOn: boolean
  onToggleSolarWind: () => void
  geomagOn: boolean
  onToggleGeomag: () => void
}

/** Timeline span: the paused slider reaches this far into the future. */
const TIMELINE_SPAN_MS = 2 * 24 * 60 * 60 * 1000 // 2 days

/** Format a future offset (ms) as e.g. "+0h", "+14h 30m", "+1d 6h", "+2d". */
function formatOffset(ms: number): string {
  const totalMin = Math.round(ms / 60000)
  const d = Math.floor(totalMin / 1440)
  const h = Math.floor((totalMin % 1440) / 60)
  const m = totalMin % 60
  if (d > 0) return `+${d}d${h > 0 ? ` ${h}h` : ''}`
  if (h > 0) return `+${h}h${m > 0 ? ` ${m}m` : ''}`
  return `+${m}m`
}

export function Hud({
  satellites,
  selectedId,
  onSelect,
  shadingOn,
  onToggleShading,
  solarWindOn,
  onToggleSolarWind,
  geomagOn,
  onToggleGeomag,
}: Props) {
  // Re-render a few times a second to mirror the (mutable) clock in the UI.
  const [, force] = useState(0)
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 250)
    const unsub = simClock.subscribe(() => force((n) => n + 1))
    return () => {
      clearInterval(id)
      unsub()
    }
  }, [])

  // Timeline scrubbing state lives on the simClock singleton (so it survives
  // this component unmounting, e.g. switching views). Pause opens the timeline
  // anchored at "now"; the slider spans [anchor, anchor + 2 days].
  const showTimeline = !simClock.playing && simClock.scrubBaseMs != null
  const scrubOffset = simClock.scrubOffsetMs()

  const selected = satellites.find((s) => s.id === selectedId)
  let info: GeodeticInfo | null = null
  let elements: ReturnType<typeof orbitalElements> | null = null
  if (selected && !selected.error) {
    info = geodeticAt(selected.satrec, simClock.date)
    elements = orbitalElements(selected.satrec)
  }

  // Alerts aren't wired up yet — placeholder counts surfaced in the pane header.
  // These will be derived from a real alerts feed later.
  const imminentAlerts = 0
  const cautionAlerts = 0

  return (
    <>
      {/* Top-left: standalone brand (no panel/bubble) */}
      <div className="brand">
        <span className="brand-dot" /> SOTERIA
        <span className="brand-sub">orbital tracker</span>
      </div>

      {/* Left column: active satellites + alerts panes */}
      <div className="left-stack">
        <div className="panel panel-pane">
          <div className="pane-title">Active Satellites</div>
          <div className="sat-list">
            {satellites.map((s) => (
              <button
                key={s.id}
                className={`sat-item ${s.id === selectedId ? 'active' : ''}`}
                onClick={() => onSelect(s.id === selectedId ? null : s.id)}
                disabled={!!s.error}
                title={s.error ?? s.description}
              >
                <span className="sat-swatch" style={{ background: s.color }} />
                <span className="sat-name">{s.name}</span>
                {s.error ? (
                  <span className="sat-err">TLE error</span>
                ) : (
                  <span
                    className="sat-danger"
                    title={DANGER_LABELS[s.danger ?? 'safe']}
                  >
                    <DangerIcon level={s.danger ?? 'safe'} />
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="panel panel-pane panel-alerts">
          <div className="pane-header">
            <span className="pane-title">Alerts</span>
            <div className="alert-counts">
              <span className="alert-count imminent" title="Imminent alerts">
                <DangerIcon level="critical" size={13} />
                {imminentAlerts}
              </span>
              <span className="alert-count caution" title="Cautionary alerts">
                <DangerIcon level="caution" size={13} />
                {cautionAlerts}
              </span>
            </div>
          </div>
          <div className="alerts-body">
            <p className="alerts-empty">No active alerts.</p>
          </div>
        </div>
      </div>

      {/* Bottom-center: clock + (when paused) timeline scrubber */}
      <div className={`panel panel-clock ${showTimeline ? 'has-timeline' : ''}`}>
        <div className="clock-row">
          <button
            className="clock-btn"
            onClick={() => simClock.togglePlay()}
            title={simClock.playing ? 'Pause & open timeline' : 'Resume live'}
          >
            {simClock.playing ? '❚❚' : '▶'}
          </button>
          <div className="clock-time">
            <div className="clock-utc">{simClock.date.toUTCString()}</div>
            <div className="clock-status">
              <span className={`live-dot ${simClock.playing ? 'on' : ''}`} />
              {simClock.playing
                ? 'LIVE · real time'
                : `timeline · ${formatOffset(scrubOffset)}`}
            </div>
          </div>
        </div>

        {showTimeline && (
          <div className="timeline">
            <input
              className="timeline-slider"
              type="range"
              min={0}
              max={TIMELINE_SPAN_MS}
              step={60000}
              value={scrubOffset}
              onChange={(e) => simClock.scrubTo(Number(e.target.value))}
            />
            <div className="timeline-labels">
              <span>now</span>
              <span>+2 days</span>
            </div>
          </div>
        )}
      </div>

      {/* Bottom-right: layer toggles, grouped in one pane */}
      <div className="panel toggle-pane">
        <div className="pane-title">Layers</div>
        <button
          className={`ui-toggle ${solarWindOn ? 'on' : ''}`}
          onClick={onToggleSolarWind}
          title="Toggle the solar-wind particle visualization"
        >
          <span className={`toggle-track ${solarWindOn ? 'on' : ''}`}>
            <span className="toggle-knob" />
          </span>
          <span className="toggle-label">
            Solar Wind
            <span className="toggle-state">{solarWindOn ? 'ON' : 'OFF'}</span>
          </span>
        </button>

        <button
          className={`ui-toggle ${geomagOn ? 'on' : ''}`}
          onClick={onToggleGeomag}
          title="Toggle the geomagnetic (auroral oval) layer"
        >
          <span className={`toggle-track ${geomagOn ? 'on' : ''}`}>
            <span className="toggle-knob" />
          </span>
          <span className="toggle-label">
            Geomagnetic
            <span className="toggle-state">{geomagOn ? 'ON' : 'OFF'}</span>
          </span>
        </button>

        <button
          className={`ui-toggle ${shadingOn ? 'on' : ''}`}
          onClick={onToggleShading}
          title="Toggle day/night shading"
        >
          <span className={`toggle-track ${shadingOn ? 'on' : ''}`}>
            <span className="toggle-knob" />
          </span>
          <span className="toggle-label">
            Day / Night Shading
            <span className="toggle-state">{shadingOn ? 'ON' : 'OFF'}</span>
          </span>
        </button>
      </div>

      {/* Right: selected satellite detail */}
      {selected && (
        <div className="panel panel-right">
          <button className="close" onClick={() => onSelect(null)}>
            ✕
          </button>
          <h2 style={{ color: selected.color }}>{selected.name}</h2>
          {selected.kind === 'real' && (
            <div className="sat-live" title="Elements refreshed from the live TLE feed every ~10 min">
              <span className="live-dot on" /> LIVE
              {selected.updatedAt && (
                <span className="sat-live-epoch">
                  · elements {new Date(selected.updatedAt).toUTCString()}
                </span>
              )}
            </div>
          )}
          <p className="desc">{selected.description}</p>
          {info && elements ? (
            <dl className="readout">
              <dt>Latitude</dt>
              <dd>{info.latitudeDeg.toFixed(3)}°</dd>
              <dt>Longitude</dt>
              <dd>{info.longitudeDeg.toFixed(3)}°</dd>
              <dt>Altitude</dt>
              <dd>{info.altitudeKm.toFixed(1)} km</dd>
              <dt>Speed</dt>
              <dd>{(info.speedKmS * 3600).toFixed(0)} km/h</dd>
              <dt>Inclination</dt>
              <dd>{elements.inclinationDeg.toFixed(2)}°</dd>
              <dt>Period</dt>
              <dd>{elements.periodMinutes.toFixed(1)} min</dd>
            </dl>
          ) : (
            <p className="desc">Propagation unavailable at this time.</p>
          )}
        </div>
      )}
    </>
  )
}
