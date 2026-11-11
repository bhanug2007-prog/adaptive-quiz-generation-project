// Require recent modulation as well as VAD: a steady fan/constant tone is not enough.
// This remains a sound heuristic, not speech recognition or speaker identification.
export function createSpeechWarningGate() {
  let frames = []
  return (level, active, now) => {
    frames.push({ level, now })
    frames = frames.filter((f) => now - f.now < 3000)
    const levels = frames.map((f) => f.level)
    return active && Math.max(...levels) - Math.min(...levels) >= 6
  }
}

// One confirmed warning per continuous incident; no media is stored here.
export function createWarningTracker(sessionId, policy, emit, { storage = globalThis.sessionStorage } = {}) {
  const key = `aiq.monitor.incidents.${sessionId}`
  let state = {}
  try { state = JSON.parse(storage?.getItem(key) || '{}') } catch { /* optional storage */ }
  // Time off-page is not evidence that a camera/audio signal persisted.
  for (const s of Object.values(state)) { if (!s.reported) s.since = null; s.normalSince = null }
  const save = () => { try { storage?.setItem(key, JSON.stringify(state)) } catch { /* optional storage */ } }
  return {
    pause(signal) {
      const s = state[signal]
      if (s && !s.reported) { s.since = null; s.normalSince = null; save() }
    },
    sample(signal, active, now = Date.now(), details = {}, eligible = true) {
      if (!policy?.persistence_ms || policy.persistence_ms[signal] == null) return
      const s = state[signal] ||= { since: null, reported: false, lastWarning: null }
      if (!active) {
        s.normalSince ??= now
        // Require recovery across samples, rather than a single missed face/audio frame.
        if (now - s.normalSince >= 1000) { s.since = null; s.reported = false; s.id = null }
      } else {
        s.normalSince = null
        // A stable sound within an open VAD episode cannot rearm an already issued warning.
        if (!eligible) { if (!s.reported) s.since = null; save(); return }
        if (s.since == null) { s.since = now; s.id = crypto.randomUUID() }
        if (!s.reported && now - s.since >= policy.persistence_ms[signal]) {
          s.reported = true
          if (s.lastWarning == null || now - s.lastWarning >= policy.cooldown_ms) {
            s.lastWarning = now
            emit('activity_warning', { at: new Date(now), duration_ms: now - s.since,
              details: { ...details, signal, incident_id: s.id } })
          }
        }
      }
      save()
    },
  }
}
