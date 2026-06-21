import type { SatelliteEntry } from '../data/satellites'
import type { SatelliteAlert } from '../lib/alerts'
import { SatelliteAlerts } from './SatelliteAlerts'

interface Props {
  satellite: SatelliteEntry
  alerts: SatelliteAlert[]
  onBack: () => void
}

/**
 * Full-screen view (reached from the Satellites screen) showing every alert for
 * one satellite — the warning descriptions and recommended command actions —
 * with a back button to return to the roster.
 */
export function SatelliteAlertView({ satellite, alerts, onBack }: Props) {
  return (
    <div className="sats-view alert-view">
      <div className="panel alert-view-panel">
        <div className="alert-view-head">
          <button className="back-btn" onClick={onBack}>
            ← Back
          </button>
          <h2 style={{ color: satellite.color }}>{satellite.name}</h2>
          <span className="alert-view-sub">
            Alerts &amp; recommended actions ({alerts.length})
          </span>
        </div>
        <div className="sat-alerts">
          <SatelliteAlerts alerts={alerts} />
        </div>
      </div>
    </div>
  )
}
