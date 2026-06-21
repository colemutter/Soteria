import type { DangerLevel } from '../data/satellites'
import { maxLevel, type SatelliteAlert } from '../lib/alerts'
import { DangerIcon } from './DangerIcon'

/**
 * Button that opens the full-screen alert view for a satellite. Renders nothing
 * when the satellite has no alerts; otherwise it's tinted to the worst severity.
 */
export function ViewAlertsButton({
  alerts,
  onClick,
}: {
  alerts: SatelliteAlert[]
  onClick: () => void
}) {
  if (alerts.length === 0) return null
  const worst = alerts.reduce<DangerLevel>(
    (lvl, a) => maxLevel(lvl, a.level),
    'safe',
  )
  return (
    <button className={`view-alerts-btn lvl-${worst}`} onClick={onClick}>
      <DangerIcon level={worst} size={15} />
      View alert{alerts.length > 1 ? 's' : ''} ({alerts.length})
      <span className="view-alerts-arrow">→</span>
    </button>
  )
}
