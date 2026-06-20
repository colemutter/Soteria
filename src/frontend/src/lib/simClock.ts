/**
 * Real-time clock — a single shared, mutable time source.
 *
 * Runs at 1× (actual wall-clock time). The 3D render loop reads `simClock.date`
 * every frame (no React re-render); the HUD subscribes for display updates.
 * `tick()` is called once per frame from a driver inside the Canvas.
 */
class SimClock {
  date: Date = new Date()
  /** When false, time is frozen at the current instant (handy for inspection). */
  playing = true

  private listeners = new Set<() => void>()

  /** Sync simulated time to the real current time (unless frozen). */
  tick() {
    if (this.playing) this.date = new Date()
  }

  togglePlay() {
    this.playing = !this.playing
    this.emit()
  }

  subscribe(fn: () => void) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private emit() {
    this.listeners.forEach((fn) => fn())
  }
}

export const simClock = new SimClock()
