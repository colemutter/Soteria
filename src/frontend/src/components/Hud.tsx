import { useEffect, useState } from 'react'
import { simClock } from '../lib/simClock'
import { geodeticAt, orbitalElements, type GeodeticInfo } from '../lib/orbital'
import { SATELLITES, type DangerLevel } from '../data/satellites'

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
  shadingOn: boolean
  onToggleShading: () => void
}

/** Status colours for the three threat levels. */
const DANGER_COLORS: Record<DangerLevel, string> = {
  safe: '#46e08a',
  caution: '#ffc24f',
  critical: '#ff5a5a',
}

const DANGER_LABELS: Record<DangerLevel, string> = {
  safe: 'Nominal — no close approaches',
  caution: 'Caution — object worth watching',
  critical: 'Critical — imminent close approach',
}

/**
 * Threat-status icon, tinted by level. `safe` shows a shield-check; `caution`
 * and `critical` show a warning triangle (distinguished by colour). The cut-out
 * marks use the panel background colour so they read on any tint.
 */
function DangerIcon({ level, size = 15 }: { level: DangerLevel; size?: number }) {
  const color = DANGER_COLORS[level]
  if (level === 'safe') {
    return (
      <svg
        className="status-icon"
        width={size}
        height={size}
        viewBox="0 0 24 24"
        style={{ color }}
        aria-hidden="true"
      >
        <path d="M12 2 4 5v6c0 5 3.4 8.6 8 10 4.6-1.4 8-5 8-10V5z" fill="currentColor" />
        <path
          d="M8.4 12l2.6 2.6L15.8 9.2"
          fill="none"
          stroke="#0c1019"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  }
  return (
    <svg
      className="status-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      style={{ color }}
      aria-hidden="true"
    >
      <path d="M12 2.5 1.2 21.5h21.6z" fill="currentColor" />
      <rect x="11" y="8.5" width="2" height="6" rx="1" fill="#0c1019" />
      <rect x="11" y="16.4" width="2" height="2" rx="1" fill="#0c1019" />
    </svg>
  )
}

export function Hud({ selectedId, onSelect, shadingOn, onToggleShading }: Props) {
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

  const selected = SATELLITES.find((s) => s.id === selectedId)
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
            {SATELLITES.map((s) => (
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

      {/* Bottom-center: real-time clock */}
      <div className="panel panel-clock">
        <button className="clock-btn" onClick={() => simClock.togglePlay()}>
          {simClock.playing ? '❚❚' : '▶'}
        </button>
        <div className="clock-time">
          <div className="clock-utc">{simClock.date.toUTCString()}</div>
          <div className="clock-status">
            <span className={`live-dot ${simClock.playing ? 'on' : ''}`} />
            {simClock.playing ? 'LIVE · real time' : 'paused'}
          </div>
        </div>
      </div>

      {/* Bottom-right: day/night shading toggle */}
      <button
        className={`panel shading-toggle ${shadingOn ? 'on' : ''}`}
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

      {/* Right: selected satellite detail */}
      {selected && (
        <div className="panel panel-right">
          <button className="close" onClick={() => onSelect(null)}>
            ✕
          </button>
          <h2 style={{ color: selected.color }}>{selected.name}</h2>
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
