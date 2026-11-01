import { useEffect, useRef, useState } from 'react'

const RM_QUERY = '(prefers-reduced-motion: reduce)'

/** True when the visitor asked the OS to reduce motion. Updates live. */
export function useReducedMotion() {
  const get = () => typeof window !== 'undefined' && !!window.matchMedia?.(RM_QUERY).matches
  const [reduced, setReduced] = useState(get)
  useEffect(() => {
    const mq = window.matchMedia?.(RM_QUERY)
    if (!mq) return undefined
    const on = () => setReduced(mq.matches)
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [])
  return reduced
}

/** Low-power heuristics: few cores or the browser's data saver. */
export function isLowPowerDevice() {
  if (typeof navigator === 'undefined') return true
  const cores = navigator.hardwareConcurrency
  const saveData = !!navigator.connection?.saveData
  return saveData || (typeof cores === 'number' && cores <= 4)
}

let webglCache
/** Cheap one-off probe for a WebGL context. */
export function hasWebGL() {
  if (webglCache !== undefined) return webglCache
  try {
    const c = document.createElement('canvas')
    const ctx = c.getContext('webgl2') || c.getContext('webgl')
    webglCache = !!ctx
    ctx?.getExtension?.('WEBGL_lose_context')?.loseContext()
  } catch {
    webglCache = false
  }
  return webglCache
}

/** Whether the hero should mount its WebGL layer at all. */
export function shouldUseWebGL(reducedMotion) {
  if (reducedMotion) return false
  if (typeof window === 'undefined') return false
  if (isLowPowerDevice()) return false
  return hasWebGL()
}

/** Tracks whether an element is in (or near) the viewport. */
export function useInView(options = {}) {
  const ref = useRef(null)
  const { once = false, rootMargin = '0px', threshold = 0 } = options
  const [inView, setInView] = useState(typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') return undefined
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setInView(true)
        if (once) io.disconnect()
      } else if (!once) {
        setInView(false)
      }
    }, { rootMargin, threshold })
    io.observe(el)
    return () => io.disconnect()
  }, [once, rootMargin, threshold])
  return [ref, inView]
}

/** Whether the tab is currently visible. */
export function usePageVisible() {
  const [visible, setVisible] = useState(typeof document === 'undefined' || document.visibilityState !== 'hidden')
  useEffect(() => {
    const on = () => setVisible(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', on)
    return () => document.removeEventListener('visibilitychange', on)
  }, [])
  return visible
}
