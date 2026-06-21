import type { SatelliteAlert } from '../lib/alerts'
import { DangerIcon } from './DangerIcon'

/**
 * Renders the alert cards for a satellite — the problem description, expected
 * impacts, and recommended command actions. Shared by the map HUD's detail
 * panel and the Satellites screen's full alert view so both stay in sync.
 */
export function SatelliteAlerts({ alerts }: { alerts: SatelliteAlert[] }) {
  return (
    <>
      {alerts.map((a) => (
        <div key={a.id} className={`sat-alert lvl-${a.level}`}>
          <div className="sat-alert-head">
            <DangerIcon level={a.level} size={14} />
            <span className="sat-alert-name">{a.title}</span>
            <span className={`sat-alert-risk lvl-${a.level}`}>{a.riskLabel}</span>
          </div>

          {(a.rationale || a.summary) && (
            <p className="sat-alert-desc">{a.rationale || a.summary}</p>
          )}

          {a.possibleOutcomes.length > 0 && (
            <div className="sat-alert-tags">
              {a.possibleOutcomes.map((o) => (
                <span key={o} className="sat-alert-tag">
                  {o}
                </span>
              ))}
            </div>
          )}

          {a.commands.length > 0 && (
            <div className="sat-alert-cmds">
              <div className="sat-alert-cmds-title">Recommended actions</div>
              {a.commands.map((c, i) => (
                <details key={`${a.id}-cmd-${i}`} className="sat-cmd" open>
                  <summary>
                    <span className="sat-cmd-label">{c.label}</span>
                    {c.humanReviewRequired && (
                      <span className="sat-cmd-flag">review</span>
                    )}
                  </summary>
                  {c.target && (
                    <div className="sat-cmd-meta">
                      <span>Target</span>
                      <code>{c.target}</code>
                    </div>
                  )}
                  {c.command && (
                    <div className="sat-cmd-meta">
                      <span>Command</span>
                      <code>{c.command}</code>
                    </div>
                  )}
                  {c.script && <pre className="sat-cmd-script">{c.script}</pre>}
                </details>
              ))}
            </div>
          )}
        </div>
      ))}
    </>
  )
}
