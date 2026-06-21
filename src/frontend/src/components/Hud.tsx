import { useEffect, useState, type FormEvent } from 'react'
import { simClock } from '../lib/simClock'
import { geodeticAt, orbitalElements, type GeodeticInfo } from '../lib/orbital'
import type { DangerLevel, SatelliteEntry } from '../data/satellites'
import { searchSatellites, type TleRecord } from '../lib/tleApi'

interface Props {
  satellites: SatelliteEntry[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  /** Add a theoretical satellite from a user-entered name + TLE. */
  onAddTheoretical: (
    name: string,
    line1: string,
    line2: string,
  ) => SatelliteEntry
  /** Add a real satellite from a looked-up live element set. */
  onAddReal: (record: TleRecord) => SatelliteEntry
  shadingOn: boolean
  onToggleShading: () => void
}

/** Which step of the add-satellite flow is showing. */
type AddMode = null | 'choose' | 'theoretical' | 'real'

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

export function Hud({
  satellites,
  selectedId,
  onSelect,
  onAddTheoretical,
  onAddReal,
  shadingOn,
  onToggleShading,
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

  // "Add satellite" flow state. `addMode` walks: closed → choose → real/theoretical.
  const [addMode, setAddMode] = useState<AddMode>(null)
  // Theoretical sub-form.
  const [newName, setNewName] = useState('')
  const [newTle, setNewTle] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  // Real (lookup) sub-form.
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<TleRecord[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)

  const closeAddForm = () => {
    setAddMode(null)
    setNewName('')
    setNewTle('')
    setAddError(null)
    setQuery('')
    setResults(null)
    setSearchError(null)
  }

  const handleAddTheoretical = (e: FormEvent) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) {
      setAddError('Enter a name for the satellite.')
      return
    }
    // Accept a pasted 2-line TLE, or a 3-line one (name + 2 lines): take the
    // last two non-empty lines as the element set.
    const lines = newTle
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
    if (lines.length < 2) {
      setAddError('Paste the two TLE element lines.')
      return
    }
    const line1 = lines[lines.length - 2]
    const line2 = lines[lines.length - 1]
    const entry = onAddTheoretical(name, line1, line2)
    if (entry.error) {
      setAddError(`Invalid trajectory data: ${entry.error}`)
      return
    }
    closeAddForm()
  }

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault()
    const q = query.trim()
    if (!q) return
    setSearching(true)
    setSearchError(null)
    setResults(null)
    try {
      const found = await searchSatellites(q)
      setResults(found)
    } catch {
      setSearchError('Lookup failed — check your connection and try again.')
    } finally {
      setSearching(false)
    }
  }

  const handlePickReal = (record: TleRecord) => {
    onAddReal(record)
    closeAddForm()
  }

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

          {addMode === null && (
            <button
              className="add-sat-toggle"
              onClick={() => setAddMode('choose')}
            >
              + Add satellite
            </button>
          )}

          {addMode === 'choose' && (
            <div className="add-sat-form">
              <p className="add-sat-prompt">What kind of satellite?</p>
              <div className="add-sat-choices">
                <button
                  className="add-sat-choice"
                  onClick={() => setAddMode('real')}
                >
                  <span className="add-sat-choice-title">Real</span>
                  <span className="add-sat-choice-sub">
                    Look up live orbital data
                  </span>
                </button>
                <button
                  className="add-sat-choice"
                  onClick={() => setAddMode('theoretical')}
                >
                  <span className="add-sat-choice-title">Theoretical</span>
                  <span className="add-sat-choice-sub">
                    Enter your own trajectory
                  </span>
                </button>
              </div>
              <div className="add-sat-actions">
                <button className="add-sat-btn" onClick={closeAddForm}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {addMode === 'theoretical' && (
            <form className="add-sat-form" onSubmit={handleAddTheoretical}>
              <input
                className="add-sat-field"
                placeholder="Satellite name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                autoFocus
              />
              <textarea
                className="add-sat-field add-sat-tle"
                placeholder={
                  'Paste TLE (two element lines)\n1 25544U 98067A   ...\n2 25544  51.6413 ...'
                }
                value={newTle}
                onChange={(e) => setNewTle(e.target.value)}
                rows={4}
                spellCheck={false}
              />
              {addError && <p className="add-sat-error">{addError}</p>}
              <div className="add-sat-actions">
                <button
                  type="button"
                  className="add-sat-btn"
                  onClick={() => setAddMode('choose')}
                >
                  Back
                </button>
                <button type="submit" className="add-sat-btn primary">
                  Add satellite
                </button>
              </div>
            </form>
          )}

          {addMode === 'real' && (
            <div className="add-sat-form">
              <form className="add-sat-search" onSubmit={handleSearch}>
                <input
                  className="add-sat-field"
                  placeholder="Search by name (e.g. Hubble, Starlink)"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  autoFocus
                />
                <button
                  type="submit"
                  className="add-sat-btn primary"
                  disabled={searching || !query.trim()}
                >
                  {searching ? '…' : 'Search'}
                </button>
              </form>

              {searchError && <p className="add-sat-error">{searchError}</p>}

              {results && results.length === 0 && (
                <p className="add-sat-empty">No satellites found.</p>
              )}

              {results && results.length > 0 && (
                <ul className="add-sat-results">
                  {results.slice(0, 8).map((r) => (
                    <li key={r.satelliteId}>
                      <button
                        className="add-sat-result"
                        onClick={() => handlePickReal(r)}
                        title={`Add ${r.name} (NORAD ${r.satelliteId})`}
                      >
                        <span className="add-sat-result-name">{r.name}</span>
                        <span className="add-sat-result-id">
                          #{r.satelliteId}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="add-sat-actions">
                <button
                  className="add-sat-btn"
                  onClick={() => setAddMode('choose')}
                >
                  Back
                </button>
              </div>
            </div>
          )}
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
