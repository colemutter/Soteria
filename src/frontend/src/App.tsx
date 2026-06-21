import { useEffect, useRef, useState } from 'react'
import { Scene } from './components/Scene'
import { Hud } from './components/Hud'
import { Navbar, type AppView } from './components/Navbar'
import { SatellitesView } from './components/SatellitesView'
import {
  SATELLITES,
  createUserSatellite,
  createRealSatellite,
  updateSatelliteTle,
  type SatelliteEntry,
} from './data/satellites'
import { fetchTleById, type TleRecord } from './lib/tleApi'
import { syncSatellites } from './lib/satelliteSync'
import { simClock } from './lib/simClock'
import './App.css'

/** How often to re-fetch live elements for `real` satellites. */
const REAL_REFRESH_MS = 10 * 60 * 1000 // ~10 minutes

function App() {
  // Which top-level view is active. 'map' is the default globe view.
  const [view, setView] = useState<AppView>('map')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // When false, the Earth shader's day/night + ocean effects are bypassed and a
  // plain, fully-lit textured globe is shown.
  const [shadingOn, setShadingOn] = useState(true)
  // Toggles the live solar-wind particle visualization.
  const [solarWindOn, setSolarWindOn] = useState(true)
  // Toggles the geomagnetic (auroral oval) layer.
  const [geomagOn, setGeomagOn] = useState(true)
  // The live satellite list: seeded with the built-ins, grown by the UI.
  const [satellites, setSatellites] = useState<SatelliteEntry[]>(SATELLITES)

  // Mirror the list into a ref so the refresh interval reads the latest without
  // resetting the timer every time a satellite is added.
  const satellitesRef = useRef(satellites)

  useEffect(() => {
    satellitesRef.current = satellites
  }, [satellites])

  /**
   * Add a theoretical satellite from a name + TLE. Returns the created entry so
   * the add form can surface a parse error; on success it's appended and
   * selected so the camera flies to it.
   */
  const addTheoretical = (
    name: string,
    line1: string,
    line2: string,
  ): SatelliteEntry => {
    const entry = createUserSatellite(name, line1, line2)
    if (!entry.error) {
      setSatellites((prev) => [...prev, entry])
      setSelectedId(entry.id)
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
      setSelectedId(existing.id)
      void syncSatellites([existing], simClock.date) // refresh its row
      return existing
    }
    if (!entry.error) {
      setSatellites((prev) => [...prev, entry])
      setSelectedId(entry.id)
      void syncSatellites([entry], simClock.date) // immediate DB write on add
    }
    return entry
  }

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

  return (
    <div className="app">
      {/* The globe stays mounted across views (preserves camera state); the
          Satellites view is a full-screen panel that sits over it. */}
      <Scene
        satellites={satellites}
        selectedId={selectedId}
        onSelect={setSelectedId}
        shadingOn={shadingOn}
        solarWindOn={solarWindOn}
        geomagOn={geomagOn}
      />

      {view === 'map' && (
        <Hud
          satellites={satellites}
          selectedId={selectedId}
          onSelect={setSelectedId}
          shadingOn={shadingOn}
          onToggleShading={() => setShadingOn((v) => !v)}
          solarWindOn={solarWindOn}
          onToggleSolarWind={() => setSolarWindOn((v) => !v)}
          geomagOn={geomagOn}
          onToggleGeomag={() => setGeomagOn((v) => !v)}
        />
      )}

      {view === 'satellites' && (
        <SatellitesView
          satellites={satellites}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onAddTheoretical={addTheoretical}
          onAddReal={addReal}
        />
      )}

      <Navbar view={view} onChangeView={setView} />
    </div>
  )
}

export default App
