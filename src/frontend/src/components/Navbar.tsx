export type AppView = 'map' | 'satellites'

interface Props {
  view: AppView
  onChangeView: (view: AppView) => void
}

const TABS: { id: AppView; label: string }[] = [
  { id: 'map', label: 'Map' },
  { id: 'satellites', label: 'Satellites' },
]

/** Top navigation bar — switches between the main views. */
export function Navbar({ view, onChangeView }: Props) {
  return (
    <nav className="navbar">
      <div className="nav-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`nav-tab ${view === t.id ? 'active' : ''}`}
            onClick={() => onChangeView(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
    </nav>
  )
}
