import { useState } from 'react'
import { Scene } from './components/Scene'
import { Hud } from './components/Hud'
import './App.css'

function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // When false, the Earth shader's day/night + ocean effects are bypassed and a
  // plain, fully-lit textured globe is shown.
  const [shadingOn, setShadingOn] = useState(true)

  return (
    <div className="app">
      <Scene selectedId={selectedId} onSelect={setSelectedId} shadingOn={shadingOn} />
      <Hud
        selectedId={selectedId}
        onSelect={setSelectedId}
        shadingOn={shadingOn}
        onToggleShading={() => setShadingOn((v) => !v)}
      />
    </div>
  )
}

export default App
