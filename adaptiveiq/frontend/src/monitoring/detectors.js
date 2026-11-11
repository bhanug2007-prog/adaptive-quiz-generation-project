// Pure detection logic for integrity monitoring, kept free of browser APIs so it can be unit-tested.
// Nothing here decides anything about a student: it turns raw signals into timed events for the lecturer to review.

/** Root-mean-square level of an audio frame in dBFS (-100 for silence). */
export function rmsDb(samples) {
  if (!samples || !samples.length) return -100
  let sum = 0
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
  const rms = Math.sqrt(sum / samples.length)
  return rms > 0 ? Math.max(-100, 20 * Math.log10(rms)) : -100
}

/**
 * Energy-based voice activity detection (VAD). It tracks the room's background level and reports a stretch of
 * sound when the level stays clearly above it. It cannot tell speech from other loud sounds (music, a cough
 * fit, traffic): it reports "speech-like sound", which is why the lecturer must review.
 *
 * push(levelDb, tMs) returns a finished segment {start, end} or null.
 */
export function createVad({
  marginDb = 15,       // this much above the background counts as sound
  floorDb = -50,       // and it must also be louder than this
  minOnMs = 300,       // sound must last this long to start a segment
  hangoverMs = 800,    // a pause shorter than this does not end the segment
  minReportMs = 1000,  // shorter segments are not reported
} = {}) {
  let noise = null
  let onSince = null
  let segStart = null
  let lastLoud = null
  const finish = (end) => {
    const seg = segStart != null && end - segStart >= minReportMs ? { start: segStart, end } : null
    segStart = null
    onSince = null
    return seg
  }
  return {
    get noiseDb() { return noise },
    get active() { return segStart != null },
    push(level, t) {
      if (noise == null) noise = level
      const loud = level > Math.max(noise + marginDb, floorDb)
      // background follows quiet frames quickly and loud frames slowly, so a steady sound (a fan) fades out in
      // about 7 s, while speech, with its pauses between words, keeps pulling the background back down
      noise = loud ? noise + (level - noise) * 0.01 : noise + (level - noise) * 0.05
      if (loud) {
        lastLoud = t
        if (onSince == null) onSince = t
        if (segStart == null && t - onSince >= minOnMs) segStart = onSince
        return null
      }
      if (segStart == null) { onSince = null; return null }
      if (t - lastLoud >= hangoverMs) return finish(lastLoud)
      return null
    },
    flush(t) { return segStart != null ? finish(lastLoud ?? t) : null },
  }
}

/**
 * Turns face counts from periodic camera checks into episodes. An episode starts only after `confirm` checks
 * in a row agree (one bad frame is ignored) and ends when one face is seen again.
 *
 * push(faceCount, tMs) returns a finished episode {kind: 'face_none' | 'face_multiple', start, end, faces} or null.
 */
export function createFaceTracker({ confirm = 2 } = {}) {
  let cand = null          // {kind, since, n, faces}
  let open = null          // confirmed episode
  const kindOf = (n) => (n === 0 ? 'face_none' : n > 1 ? 'face_multiple' : null)
  const close = (t) => {
    const ep = open ? { kind: open.kind, start: open.since, end: t, faces: open.faces } : null
    open = null
    return ep
  }
  return {
    get open() { return open?.kind || null },
    push(count, t) {
      const kind = kindOf(count)
      if (open && kind === open.kind) { open.faces = Math.max(open.faces, count); return null }
      let done = null
      if (open) done = close(t)
      if (!kind) { cand = null; return done }
      if (cand && cand.kind === kind) {
        cand.n += 1
        cand.faces = Math.max(cand.faces, count)
      } else {
        cand = { kind, since: t, n: 1, faces: count }
      }
      if (cand.n >= confirm) { open = { ...cand }; cand = null }
      return done
    },
    flush(t) { cand = null; return close(t) },
  }
}
