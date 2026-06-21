import { useEffect, useMemo, useRef, useState } from 'react'
import { Scene } from './components/Scene'
import { Hud } from './components/Hud'
import { Navbar, type AppView } from './components/Navbar'
import { SatellitesView } from './components/SatellitesView'
import { SatelliteAlertView } from './components/SatelliteAlertView'
import { WeatherView } from './components/WeatherView'
import {
  SATELLITES,
  createUserSatellite,
  createRealSatellite,
  updateSatelliteTle,
  type DangerLevel,
  type SatelliteEntry,
} from './data/satellites'
import { fetchTleById, type TleRecord } from './lib/tleApi'
import { syncSatellites } from './lib/satelliteSync'
import { rememberSatellite, fetchAllDbSatellites } from './lib/savedSatellites'
import { fetchSatelliteAlerts, maxLevel, type SatelliteAlert } from './lib/alerts'
import { simClock } from './lib/simClock'
import './App.css'

/** How often to re-fetch live elements for `real` satellites. */
const REAL_REFRESH_MS = 10 * 60 * 1000 // ~10 minutes
/** How often to re-fetch satellite alerts (runbooks + event reports). */
const ALERTS_REFRESH_MS = 10 * 60 * 1000 // ~10 minutes

function App() {
  // Which top-level view is active. 'map' is the default globe view.
  const [view, setView] = useState<AppView>('map')
  // Map selection (drives the globe camera + detail panel).
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // When set, the full-screen alert view for this satellite is shown as an
  // overlay (reachable from both the map HUD and the Satellites screen).
  const [alertViewId, setAlertViewId] = useState<string | null>(null)
  // Satellites-screen selection — independent of the map, so picking a
  // satellite there only shows its model/details and doesn't move the globe.
  const [satSelectedId, setSatSelectedId] = useState<string | null>(null)
  // When false, the Earth shader's day/night + ocean effects are bypassed and a
  // plain, fully-lit textured globe is shown.
  const [shadingOn, setShadingOn] = useState(true)
  // Toggles the live solar-wind particle visualization.
  const [solarWindOn, setSolarWindOn] = useState(true)
  // Toggles the geomagnetic (auroral oval) layer.
  const [geomagOn, setGeomagOn] = useState(true)
  // Demo mode: feeds the layers a synthetic escalating-storm dataset.
  const [demoOn, setDemoOn] = useState(false)
  // The live satellite list: seeded with the built-ins, grown by the UI.
  const [satellites, setSatellites] = useState<SatelliteEntry[]>(SATELLITES)
  // Active alerts from the runbook / event-report pipeline (polled).
  const [alerts, setAlerts] = useState<SatelliteAlert[]>([])

  // Mirror the list into a ref so the refresh interval reads the latest without
  // resetting the timer every time a satellite is added.
  const satellitesRef = useRef(satellites)

  useEffect(() => {
    satellitesRef.current = satellites
  }, [satellites])

  /**
   * Add a theoretical satellite from a name + TLE. Returns the created entry so
   * the add form can surface a parse error; on success it's appended and
   * selected in the Satellites screen (where the add happens — not the map).
   */
  const addTheoretical = (
    name: string,
    line1: string,
    line2: string,
  ): SatelliteEntry => {
    const entry = createUserSatellite(name, line1, line2)
    if (!entry.error) {
      setSatellites((prev) => [...prev, entry])
      setSatSelectedId(entry.id)
      rememberSatellite(entry.id) // persist across reloads in this browser
      void syncSatellites([entry], simClock.date) // immediate DB write on add
    }
    return entry
  }

  /**
   * Add a real satellite from a live TLE-API record. De-duplicates by NORAD id
   * (selecting the existing one instead of adding a copy).
   */
  const addReal = (record: TleRecord): SatelliteEntry => {
    const entry = createRealSatellite(record)
    const existing = satellitesRef.current.find((s) => s.id === entry.id)
    if (existing) {
      setSatSelectedId(existing.id)
      rememberSatellite(existing.id)
      void syncSatellites([existing], simClock.date) // refresh its row
      return existing
    }
    if (!entry.error) {
      setSatellites((prev) => [...prev, entry])
      setSatSelectedId(entry.id)
      rememberSatellite(entry.id) // persist across reloads in this browser
      void syncSatellites([entry], simClock.date) // immediate DB write on add
    }
    return entry
  }

  // Restore satellites already persisted in the DB.
  useEffect(() => {
    let active = true
    void fetchAllDbSatellites().then((saved) => {
      if (!active || saved.length === 0) return
      setSatellites((prev) => {
        const seen = new Set(prev.map((s) => s.id))
        const additions = saved.filter((s) => !seen.has(s.id))
        return additions.length ? [...prev, ...additions] : prev
      })
    })
    return () => {
      active = false
    }
  }, [])

  // Mirror the initial (built-in) list to the DB once on load.
  useEffect(() => {
    void syncSatellites(satellitesRef.current, simClock.date)
  }, [])

  // Every ~10 min: refresh real satellites' elements, then mirror the whole list
  // to Supabase with current positions (the DB write follows the live update).
  useEffect(() => {
    const refresh = async () => {
      const current = satellitesRef.current
      const reals = current.filter((s) => s.kind === 'real' && s.noradId != null)
      let next = current
      if (reals.length > 0) {
        const updates = await Promise.all(
          reals.map(async (s) => {
            try {
              const rec = await fetchTleById(s.noradId!)
              return { id: s.id, rec }
            } catch {
              return null // keep the old elements if a refresh fails
            }
          }),
        )
        next = current.map((p) => {
          const u = updates.find((x) => x && x.id === p.id)
          return u
            ? updateSatelliteTle(p, u.rec.line1, u.rec.line2, u.rec.date)
            : p
        })
        setSatellites(next)
      }
      await syncSatellites(next, simClock.date)
    }
    const id = setInterval(refresh, REAL_REFRESH_MS)
    return () => clearInterval(id)
  }, [])

  // Poll the alert feed (command runbooks + event reports) every ~10 min, plus
  // once on load, so satellite statuses and the Alerts pane stay current.
  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const next = await fetchSatelliteAlerts()
        if (active) setAlerts(next)
      } catch (e) {
        console.error('[alerts] fetch failed', e)
      }
    }
    void load()
    const id = setInterval(() => void load(), ALERTS_REFRESH_MS)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [])

  // Highest danger level per satellite, derived from its alerts.
  const dangerById = useMemo(() => {
    const m = new Map<string, DangerLevel>()
    for (const a of alerts) {
      m.set(a.satelliteId, maxLevel(m.get(a.satelliteId) ?? 'safe', a.level))
    }
    return m
  }, [alerts])

  // Alerts grouped by satellite, for the detail panel.
  const alertsBySatellite = useMemo(() => {
    const m = new Map<string, SatelliteAlert[]>()
    for (const a of alerts) {
      const list = m.get(a.satelliteId)
      if (list) list.push(a)
      else m.set(a.satelliteId, [a])
    }
    return m
  }, [alerts])

  // Overlay alert-derived danger onto the satellites so status badges (HUD list,
  // Satellites screen) reflect the live alert feed instead of the static default.
  const displaySatellites = useMemo(
    () =>
      satellites.map((s) => {
        const level = dangerById.get(s.id)
        return level && level !== s.danger ? { ...s, danger: level } : s
      }),
    [satellites, dangerById],
  )

  // Close the alert overlay when switching top-level views.
  useEffect(() => setAlertViewId(null), [view])

  // The satellite + alerts backing the overlay (null when it's closed or the
  // satellite has no alerts).
  const alertViewSatellite = alertViewId
    ? displaySatellites.find((s) => s.id === alertViewId)
    : undefined
  const alertViewAlerts = alertViewId
    ? alertsBySatellite.get(alertViewId) ?? []
    : []

  return (
    <div className="app">
      {/* The globe stays mounted across views (preserves camera state); the
          Satellites view is a full-screen panel that sits over it. */}
      <Scene
        satellites={displaySatellites}
        selectedId={selectedId}
        onSelect={setSelectedId}
        shadingOn={shadingOn}
        solarWindOn={solarWindOn}
        geomagOn={geomagOn}
        demoOn={demoOn}
      />

      {view === 'map' && (
        <Hud
          satellites={displaySatellites}
          alerts={alerts}
          alertsBySatellite={alertsBySatellite}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onOpenAlerts={setAlertViewId}
          shadingOn={shadingOn}
          onToggleShading={() => setShadingOn((v) => !v)}
          solarWindOn={solarWindOn}
          onToggleSolarWind={() => setSolarWindOn((v) => !v)}
          geomagOn={geomagOn}
          onToggleGeomag={() => setGeomagOn((v) => !v)}
          demoOn={demoOn}
          onToggleDemo={() => setDemoOn((v) => !v)}
        />
      )}

      {view === 'satellites' && (
        <SatellitesView
          satellites={displaySatellites}
          alertsBySatellite={alertsBySatellite}
          selectedId={satSelectedId}
          onSelect={setSatSelectedId}
          onOpenAlerts={setAlertViewId}
          onAddTheoretical={addTheoretical}
          onAddReal={addReal}
        />
      )}

      {view === 'weather' && <WeatherView demo={demoOn} />}

      {alertViewSatellite && alertViewAlerts.length > 0 && (
        <SatelliteAlertView
          satellite={alertViewSatellite}
          alerts={alertViewAlerts}
          onBack={() => setAlertViewId(null)}
        />
      )}

      <Navbar view={view} onChangeView={setView} />
    </div>
  )
}

export default App
