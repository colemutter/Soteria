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
  /**
   * Anchor (ms epoch) for timeline scrubbing — the "now" captured when paused.
   * Null while playing. Held on the singleton (not React state) so it survives
   * components unmounting/remounting (e.g. switching views).
   */
  scrubBaseMs: number | null = null

  private listeners = new Set<() => void>()

  /** Sync simulated time to the real current time (unless frozen). */
  tick() {
    if (this.playing) this.date = new Date()
  }

  togglePlay() {
    if (this.playing) this.beginScrub()
    else this.play()
  }

  /** Resume live (real-time) tracking and close the timeline. */
  play() {
    this.playing = true
    this.scrubBaseMs = null
    this.emit()
  }

  /** Pause and open the timeline, anchored at the current real time. */
  beginScrub() {
    this.scrubBaseMs = Date.now()
    this.date = new Date(this.scrubBaseMs)
    this.playing = false
    this.emit()
  }

  /** Move the simulated time to `offsetMs` past the scrub anchor. */
  scrubTo(offsetMs: number) {
    if (this.scrubBaseMs == null) return
    this.date = new Date(this.scrubBaseMs + offsetMs)
    this.emit()
  }

  /** Current scrub offset (ms past the anchor); 0 when not scrubbing. */
  scrubOffsetMs(): number {
    return this.scrubBaseMs == null
      ? 0
      : this.date.getTime() - this.scrubBaseMs
  }

  /** Set the simulated time explicitly. No lasting effect while playing. */
  setDate(date: Date) {
    this.date = date
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
