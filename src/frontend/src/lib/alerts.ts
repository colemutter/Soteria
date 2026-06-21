import { supabase, warnNoSupabaseOnce } from './supabase'
import type { DangerLevel } from '../data/satellites'

/**
 * Satellite alerts read from the AI/report pipeline tables in Supabase:
 *
 *   - `command_runbooks`        — per-satellite actionable runbooks: a problem
 *     summary plus catalog-backed command steps (the "what to do"). The matching
 *     event findings (the "what's wrong") ride along in `metadata.findings`.
 *   - `satellite_event_reports` — validated event-window reports whose
 *     `report_json.findings[]` describe each affected satellite's impact. Used to
 *     surface problems for satellites that don't (yet) have a runbook.
 *
 * Both tables are anon-readable, so the frontend queries them directly (like the
 * SWPC space-weather data). An alert is keyed to a satellite by its frontend
 * `id`, which equals `satellite_external_id` / `findings[].satellite_id`
 * (e.g. "iss", "gps", "real-33591").
 */

/** A single recommended command step attached to a runbook alert. */
export interface AlertCommand {
  /** Short label — the catalog command id (e.g. "adcs_set_sunsafe"). */
  label: string
  /** Subsystem / target the command is addressed to. */
  target?: string
  /** Raw command mnemonic, if present. */
  command?: string
  /** Human-reviewable rendered script (OpenC3 Ruby snippet). */
  script?: string
  humanReviewRequired?: boolean
  automatedAllowed?: boolean
}

/** One alert affecting one satellite. */
export interface SatelliteAlert {
  /** Stable id (table row id, or row id + finding index for reports). */
  id: string
  source: 'runbook' | 'report'
  /** Frontend satellite id this alert is about. */
  satelliteId: string
  satelliteName?: string
  title: string
  /** Event-level summary of the situation. */
  summary: string
  /** Per-satellite impact rationale (the description of the problem). */
  rationale?: string
  level: DangerLevel
  /** Human-readable risk/severity label (e.g. "High", "Major"). */
  riskLabel: string
  /** Expected effects, human-readable (e.g. "Increased Drag"). */
  possibleOutcomes: string[]
  commands: AlertCommand[]
  createdAt: string | null
  /** Space-weather event window this alert belongs to (for "danger passed"). */
  eventWindowId: string | null
}

const LEVEL_RANK: Record<DangerLevel, number> = { safe: 0, caution: 1, critical: 2 }

/** The more severe of two danger levels. */
export function maxLevel(a: DangerLevel, b: DangerLevel): DangerLevel {
  return LEVEL_RANK[a] >= LEVEL_RANK[b] ? a : b
}

/** Ordering of event-impact severities (from the report pipeline). */
const SEVERITY_RANK: Record<string, number> = {
  none: 0,
  minor: 1,
  moderate: 2,
  major: 3,
  severe: 4,
  extreme: 5,
}

/** The worst severity string among a set of findings, or '' if none. */
function worstSeverity(findings: Record<string, unknown>[]): string {
  let worst = ''
  for (const f of findings) {
    const s = ((f.severity as string) ?? '').toLowerCase()
    if (!(s in SEVERITY_RANK)) continue
    if (!worst || SEVERITY_RANK[s] > SEVERITY_RANK[worst]) worst = s
  }
  return worst
}

/** Map a runbook `risk_level` to a HUD danger level. */
function levelFromRisk(risk?: string | null): DangerLevel {
  switch ((risk ?? '').toLowerCase()) {
    case 'high':
    case 'critical':
    case 'severe':
    case 'extreme':
      return 'critical'
    case 'medium':
    case 'moderate':
    case 'low':
    case 'minor':
    case 'caution':
      return 'caution'
    default:
      return 'safe'
  }
}

/** Map a report finding `severity` to a HUD danger level. */
function levelFromSeverity(sev?: string | null): DangerLevel {
  switch ((sev ?? '').toLowerCase()) {
    case 'major':
    case 'severe':
    case 'extreme':
      return 'critical'
    case 'moderate':
    case 'minor':
      return 'caution'
    default:
      return 'safe'
  }
}

/** "increased_drag" / "high" → "Increased Drag" / "High". */
function humanize(value?: string | null): string {
  if (!value) return ''
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function uniq(values: string[]): string[] {
  return [...new Set(values)]
}

/* The raw row shapes are loosely typed — the JSONB columns vary by pipeline
 * version, so we read defensively rather than assert a rigid schema. */
type RunbookRow = {
  id: string
  satellite_external_id: string | null
  title: string | null
  summary: string | null
  commands: unknown
  risk_level: string | null
  metadata: Record<string, unknown> | null
  created_at: string | null
  event_window_id: string | null
  demo: boolean | null
}

type ReportRow = {
  id: string
  report_json: Record<string, unknown> | null
  created_at: string | null
  demo: boolean | null
}

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? (value as Record<string, unknown>[]) : []
}

function commandToItem(raw: Record<string, unknown>): AlertCommand {
  return {
    label:
      (raw.catalog_command_id as string) ||
      (raw.command as string) ||
      'command',
    target: (raw.target as string) || undefined,
    command: (raw.command as string) || undefined,
    script: (raw.rendered_script as string) || undefined,
    humanReviewRequired: Boolean(raw.human_review_required),
    automatedAllowed: Boolean(raw.automated_allowed),
  }
}

function runbookToAlert(row: RunbookRow): SatelliteAlert | null {
  const meta = row.metadata ?? {}
  const sat = (meta.satellite as Record<string, unknown>) ?? {}
  const satelliteId =
    row.satellite_external_id ?? (sat.external_id as string) ?? null
  if (!satelliteId) return null

  const findings = asArray(meta.findings)
  // Severity comes from the event-impact findings — NOT `risk_level`, which is
  // the command-automation risk and is ~always "high". Fall back to risk_level
  // only when a runbook carries no findings.
  const worst = worstSeverity(findings)
  const level = worst ? levelFromSeverity(worst) : levelFromRisk(row.risk_level)
  const riskLabel = worst
    ? humanize(worst)
    : humanize(row.risk_level) || 'Unknown'

  const rationale =
    findings
      .map((f) => f.rationale as string)
      .filter(Boolean)
      .join('\n\n') || undefined
  const outcomes = uniq(
    findings.flatMap((f) => (f.possible_outcomes as string[]) ?? []),
  ).map(humanize)

  return {
    id: row.id,
    source: 'runbook',
    satelliteId,
    satelliteName: (sat.name as string) || undefined,
    title: row.title || 'Command runbook',
    summary: row.summary || '',
    rationale,
    level,
    riskLabel,
    possibleOutcomes: outcomes,
    commands: asArray(row.commands).map(commandToItem),
    createdAt: row.created_at,
    eventWindowId: row.event_window_id,
  }
}

function reportToAlerts(row: ReportRow): SatelliteAlert[] {
  const rj = row.report_json ?? {}
  const findings = asArray(rj.findings)
  const eventSeverity = humanize(rj.event_severity as string)
  const summary = (rj.summary as string) || ''
  const eventWindowId = (rj.event_window_id as string) || null

  const out: SatelliteAlert[] = []
  findings.forEach((f, i) => {
    const satelliteId = (f.satellite_id as string) || null
    if (!satelliteId) return
    out.push({
      id: `${row.id}:${satelliteId}:${i}`,
      source: 'report',
      satelliteId,
      title: eventSeverity
        ? `${eventSeverity} space-weather event`
        : 'Space-weather event',
      summary,
      rationale: (f.rationale as string) || undefined,
      level: levelFromSeverity(f.severity as string),
      riskLabel: humanize(f.severity as string) || 'Unknown',
      possibleOutcomes: uniq((f.possible_outcomes as string[]) ?? []).map(
        humanize,
      ),
      commands: [],
      createdAt: row.created_at,
      eventWindowId,
    })
  })
  return out
}

/**
 * Fetch the end times of the given event windows, keyed by id. Used to drop
 * alerts whose danger has already passed. The stored `status` column can lag, so
 * we compare `window_end` to "now" directly. Returns an empty map on error so
 * filtering fails open (alerts are kept rather than wrongly hidden).
 */
async function fetchEventWindowEnds(
  ids: string[],
): Promise<Map<string, number>> {
  const ends = new Map<string, number>()
  if (!supabase || ids.length === 0) return ends
  const { data, error } = await supabase
    .from('space_weather_event_windows')
    .select('id,window_end')
    .in('id', ids)
  if (error) {
    console.error('[alerts] event-window query failed', error)
    return ends
  }
  for (const row of (data ?? []) as { id: string; window_end: string }[]) {
    const t = Date.parse(row.window_end)
    if (!Number.isNaN(t)) ends.set(row.id, t)
  }
  return ends
}

// How many recent rows to pull. Runbooks are per-satellite/per-event so we want
// a generous window; reports are coarser (one per event window).
const RUNBOOK_LIMIT = 200
const REPORT_LIMIT = 50

/**
 * Fetch current satellite alerts, newest first. Runbooks take precedence per
 * satellite (they carry the actionable commands); event-report findings fill in
 * problems for satellites that don't have a runbook yet. Returns [] when
 * Supabase isn't configured or on error (the HUD just shows no alerts).
 */
export async function fetchSatelliteAlerts(demo = false): Promise<SatelliteAlert[]> {
  if (!supabase) {
    warnNoSupabaseOnce()
    return []
  }

  const [runbookRes, reportRes] = await Promise.all([
    supabase
      .from('command_runbooks')
      .select(
        'id,satellite_external_id,title,summary,commands,risk_level,metadata,created_at,event_window_id,demo',
      )
      .eq('demo', demo)
      .order('created_at', { ascending: false })
      .limit(RUNBOOK_LIMIT),
    supabase
      .from('satellite_event_reports')
      .select('id,report_json,created_at,demo')
      .eq('demo', demo)
      .order('created_at', { ascending: false })
      .limit(REPORT_LIMIT),
  ])

  if (runbookRes.error) {
    console.error('[alerts] command_runbooks query failed', runbookRes.error)
  }
  if (reportRes.error) {
    console.error(
      '[alerts] satellite_event_reports query failed',
      reportRes.error,
    )
  }

  // Build all candidate alerts (newest-first), keeping runbook precedence.
  const runbookAlerts = ((runbookRes.data ?? []) as RunbookRow[])
    .map(runbookToAlert)
    .filter((a): a is SatelliteAlert => a !== null)
  const reportAlerts = ((reportRes.data ?? []) as ReportRow[]).flatMap(
    reportToAlerts,
  )

  // Drop alerts whose event window has already ended ("danger has passed").
  // Filter BEFORE de-duping so a satellite whose newest alert has passed can
  // still surface an older alert that's still active.
  const windowIds = uniq(
    [...runbookAlerts, ...reportAlerts]
      .map((a) => a.eventWindowId)
      .filter((id): id is string => !!id),
  )
  const ends = await fetchEventWindowEnds(windowIds)
  const now = Date.now()
  const isActive = (a: SatelliteAlert) => {
    if (!a.eventWindowId) return true // unknown timing — keep it
    const end = ends.get(a.eventWindowId)
    return end === undefined || end >= now // keep if window unknown or not ended
  }

  const alerts: SatelliteAlert[] = []
  const covered = new Set<string>()

  for (const alert of runbookAlerts) {
    if (!isActive(alert)) continue
    // Newest-first, so the first active alert seen for a satellite is its most
    // recent; skip any older ones so each satellite shows just one.
    if (covered.has(alert.satelliteId)) continue
    alerts.push(alert)
    covered.add(alert.satelliteId)
  }

  for (const alert of reportAlerts) {
    if (!isActive(alert)) continue
    // Skip satellites already described by a runbook (or an earlier report) so
    // each satellite shows a single, most-actionable alert.
    if (covered.has(alert.satelliteId)) continue
    alerts.push(alert)
    covered.add(alert.satelliteId)
  }

  return alerts
}
