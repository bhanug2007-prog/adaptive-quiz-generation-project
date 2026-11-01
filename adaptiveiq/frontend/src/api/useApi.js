import { useCallback, useEffect, useRef, useState } from 'react'

/** Loads data on mount and when deps change. Returns {data, error, loading, reload, setData}. */
export function useApi(fn, deps = []) {
  const [state, setState] = useState({ data: undefined, error: null, loading: true })
  const seq = useRef(0)
  const load = useCallback(async () => {
    const n = ++seq.current
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await fn()
      if (n === seq.current) setState({ data, error: null, loading: false })
    } catch (error) {
      if (n === seq.current) setState({ data: undefined, error, loading: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { load() }, [load])
  const setData = useCallback((updater) => setState((s) => ({ ...s, data: typeof updater === 'function' ? updater(s.data) : updater })), [])
  return { ...state, reload: load, setData }
}

/** Wraps an async action with a busy flag and error capture. */
export function useAction(fn) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = useCallback(async (...args) => {
    setBusy(true)
    setError(null)
    try {
      return await fn(...args)
    } catch (e) {
      setError(e)
      throw e
    } finally {
      setBusy(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fn])
  return { run, busy, error, setError }
}
