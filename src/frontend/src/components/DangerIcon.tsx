import type { DangerLevel } from '../data/satellites'

/** Status colours for the three threat levels. */
export const DANGER_COLORS: Record<DangerLevel, string> = {
  safe: '#46e08a',
  caution: '#ffc24f',
  critical: '#ff5a5a',
}

export const DANGER_LABELS: Record<DangerLevel, string> = {
  safe: 'Nominal — no close approaches',
  caution: 'Caution — object worth watching',
  critical: 'Critical — imminent close approach',
}

/**
 * Threat-status icon, tinted by level. `safe` shows a shield-check; `caution`
 * and `critical` show a warning triangle (distinguished by colour). The cut-out
 * marks use the panel background colour so they read on any tint.
 */
export function DangerIcon({
  level,
  size = 15,
}: {
  level: DangerLevel
  size?: number
}) {
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
