import { useCallback, useEffect, useRef, useState } from 'react'
import { generationApi } from '../api/endpoints'

const ACTIVE = ['queued', 'running']

/** Polls a generation run until it finishes. Survives re-mounts: pass the run id you stored. */
export function useGenerationRun(runId, { interval = 1500 } = {}) {
  const [run, setRun] = useState(null)
  const [error, setError] = useState(null)
  const timer = useRef()
  useEffect(() => {
    if (!runId) { setRun(null); return undefined }
    let alive = true
    const tick = async () => {
      try {
        const r = await generationApi.get(runId)
        if (!alive) return
        setRun(r)
        setError(null)
        if (ACTIVE.includes(r.status)) timer.current = setTimeout(tick, interval)
      } catch (e) {
        if (!alive) return
        setError(e)
        timer.current = setTimeout(tick, interval * 3)
      }
    }
    tick()
    return () => { alive = false; clearTimeout(timer.current) }
  }, [runId, interval])
  const cancel = useCallback(async () => {
    if (!runId) return
    const r = await generationApi.cancel(runId)
    setRun(r)
  }, [runId])
  return { run, error, cancel, active: run ? ACTIVE.includes(run.status) : !!runId }
}
