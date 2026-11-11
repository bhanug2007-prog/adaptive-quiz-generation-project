// Sends monitoring events in small batches. Events wait in sessionStorage while the network is down and are
// sent again later; the server ignores a sequence number it already has, so a retry never duplicates.

const KEY = (sid) => `aiq.monitor.${sid}`

function load(storage, sid) {
  try {
    const v = JSON.parse(storage?.getItem(KEY(sid)) || 'null')
    if (v && Array.isArray(v.pending) && Number.isInteger(v.seq)) return v
  } catch { /* storage blocked or corrupt: start fresh */ }
  return { seq: 0, pending: [] }
}

export function createEventQueue(sessionId, send, { storage = globalThis.sessionStorage, batch = 50, startSeq = 0 } = {}) {
  const st = load(storage, sessionId)
  st.seq = Math.max(st.seq, startSeq)
  let busy = null
  let stopped = false
  const save = () => { try { storage?.setItem(KEY(sessionId), JSON.stringify(st)) } catch { /* keep in memory */ } }

  const flush = async () => {
    if (busy) return busy
    busy = (async () => {
      while (st.pending.length) {
        const chunk = st.pending.slice(0, batch)
        try {
          await send(chunk)
        } catch (e) {
          // 4xx other than a conflict means these events will never be accepted (attempt over, not monitored)
          if (e && e.status && e.status >= 400 && e.status < 500 && e.status !== 409 && e.status !== 429) {
            st.pending.splice(0, chunk.length)
            save()
            continue
          }
          return false
        }
        st.pending.splice(0, chunk.length)
        save()
      }
      return true
    })()
    try { return await busy } finally { busy = null }
  }

  return {
    add(kind, { at = new Date(), duration_ms = null, details = {} } = {}) {
      if (stopped) return null
      st.seq += 1
      const ev = { seq: st.seq, kind, at: (at instanceof Date ? at : new Date(at)).toISOString(), duration_ms, details }
      st.pending.push(ev)
      save()
      return ev
    },
    flush,
    get pending() { return st.pending.length },
    get seq() { return st.seq },
    stop() { stopped = true },
    clear() { try { storage?.removeItem(KEY(sessionId)) } catch { /* ignore */ } },
  }
}
