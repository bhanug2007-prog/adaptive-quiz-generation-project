import { useEffect, useState } from 'react'
import { healthApi } from '../api/endpoints'

/** Polls /api/health. state: checking | ok | loading | offline | error */
export function useModelHealth(intervalMs = 20000) {
  const [h, setH] = useState({ state: 'checking', detail: null, raw: null })
  useEffect(() => {
    let alive = true
    let timer
    const tick = async () => {
      try {
        const r = await healthApi.get()
        const m = r.model || {}
        const state = m.state === 'ok' ? 'ok' : m.state === 'unreachable' ? 'offline' : (m.detail || '').includes('loading') ? 'loading' : 'error'
        if (alive) setH({ state, detail: m.detail, raw: r })
      } catch (e) {
        if (alive) setH({ state: 'offline', detail: e.message, raw: null })
      }
      if (alive) timer = setTimeout(tick, intervalMs)
    }
    tick()
    return () => { alive = false; clearTimeout(timer) }
  }, [intervalMs])
  return h
}
