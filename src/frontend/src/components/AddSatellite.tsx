import { useState, type FormEvent } from 'react'
import type { SatelliteEntry } from '../data/satellites'
import { searchSatellites, type TleRecord } from '../lib/tleApi'

/** Which step of the add-satellite flow is showing. */
type AddMode = null | 'choose' | 'theoretical' | 'real'

interface Props {
  /** Add a theoretical satellite from a user-entered name + TLE. */
  onAddTheoretical: (name: string, line1: string, line2: string) => SatelliteEntry
  /** Add a real satellite from a looked-up live element set. */
  onAddReal: (record: TleRecord) => SatelliteEntry
}

/**
 * The "Add satellite" flow — a `+ Add satellite` toggle that expands into a
 * real-vs-theoretical chooser, then either a live name lookup or a manual
 * TLE-entry form. Self-contained; the parent just supplies the add callbacks.
 */
export function AddSatellite({ onAddTheoretical, onAddReal }: Props) {
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

  return (
    <>
      {addMode === null && (
        <button className="add-sat-toggle" onClick={() => setAddMode('choose')}>
          + Add satellite
        </button>
      )}

      {addMode === 'choose' && (
        <div className="add-sat-form">
          <p className="add-sat-prompt">What kind of satellite?</p>
          <div className="add-sat-choices">
            <button className="add-sat-choice" onClick={() => setAddMode('real')}>
              <span className="add-sat-choice-title">Real</span>
              <span className="add-sat-choice-sub">Look up live orbital data</span>
            </button>
            <button
              className="add-sat-choice"
              onClick={() => setAddMode('theoretical')}
            >
              <span className="add-sat-choice-title">Custom</span>
              <span className="add-sat-choice-sub">Enter your own trajectory</span>
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
                    <span className="add-sat-result-id">#{r.satelliteId}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="add-sat-actions">
            <button className="add-sat-btn" onClick={() => setAddMode('choose')}>
              Back
            </button>
          </div>
        </div>
      )}
    </>
  )
}
