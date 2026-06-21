import { useEffect, useState } from 'react'
import { simClock } from '../lib/simClock'
import { geodeticAt, orbitalElements, type GeodeticInfo } from '../lib/orbital'
import type { SatelliteEntry } from '../data/satellites'
import type { TleRecord } from '../lib/tleApi'
import type { SatelliteAlert } from '../lib/alerts'
import { DangerIcon, DANGER_LABELS } from './DangerIcon'
import { AddSatellite } from './AddSatellite'
import { ModelViewer } from './ModelViewer'
import { ViewAlertsButton } from './ViewAlertsButton'

interface Props {
  satellites: SatelliteEntry[]
  alertsBySatellite: Map<string, SatelliteAlert[]>
  selectedId: string | null
  onSelect: (id: string | null) => void
  onOpenAlerts: (id: string) => void
  onAddTheoretical: (name: string, line1: string, line2: string) => SatelliteEntry
  onAddReal: (record: TleRecord) => SatelliteEntry
}

const KIND_LABEL: Record<string, string> = {
  real: 'Real · live elements',
  theoretical: 'Custom',
  builtin: 'Built-in',
}

/**
 * The "Satellites" management screen: a roster (with the add-satellite flow) on
 * the left, and the selected satellite's 3D model with its details on the right.
 */
export function SatellitesView({
  satellites,
  alertsBySatellite,
  selectedId,
  onSelect,
  onOpenAlerts,
  onAddTheoretical,
  onAddReal,
}: Props) {
  // Re-render a few times a second so the live readout (lat/lon/alt) ticks.
  const [, force] = useState(0)
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 250)
    const unsub = simClock.subscribe(() => force((n) => n + 1))
    return () => {
      clearInterval(id)
      unsub()
    }
  }, [])

  const selected = satellites.find((s) => s.id === selectedId)
  const selectedAlerts = selected
    ? alertsBySatellite.get(selected.id) ?? []
    : []
  let info: GeodeticInfo | null = null
  let elements: ReturnType<typeof orbitalElements> | null = null
  if (selected && !selected.error) {
    info = geodeticAt(selected.satrec, simClock.date)
    elements = orbitalElements(selected.satrec)
  }

  return (
    <div className="sats-view">
      {/* Left: roster + add */}
      <div className="panel sats-roster">
        <div className="pane-title">Satellites</div>
        <div className="sat-list">
          {satellites.map((s) => (
            <button
              key={s.id}
              className={`sat-item ${s.id === selectedId ? 'active' : ''}`}
              onClick={() => onSelect(s.id)}
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
        <AddSatellite onAddTheoretical={onAddTheoretical} onAddReal={onAddReal} />
      </div>

      {/* Right: model + details */}
      <div className="sats-detail">
        {selected ? (
          <>
            <div className="panel model-stage">
              {selected.model ? (
                <ModelViewer key={selected.model.url} url={selected.model.url} />
              ) : (
                <div className="model-empty">No model available.</div>
              )}
              <div className="model-hint">drag to rotate · scroll to zoom</div>
            </div>

            <div className="panel sats-details-card">
              <div className="sats-details-head">
                <h2 style={{ color: selected.color }}>{selected.name}</h2>
                <span className="sats-kind">
                  {KIND_LABEL[selected.kind ?? 'builtin'] ?? 'Built-in'}
                </span>
              </div>
              {selected.kind === 'real' && selected.updatedAt && (
                <div className="sat-live">
                  <span className="live-dot on" /> LIVE
                  <span className="sat-live-epoch">
                    · elements {new Date(selected.updatedAt).toUTCString()}
                  </span>
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

              <ViewAlertsButton
                alerts={selectedAlerts}
                onClick={() => selected && onOpenAlerts(selected.id)}
              />
            </div>
          </>
        ) : (
          <div className="panel sats-empty">
            <p>Select a satellite to view its model and details.</p>
          </div>
        )}
      </div>
    </div>
  )
}
