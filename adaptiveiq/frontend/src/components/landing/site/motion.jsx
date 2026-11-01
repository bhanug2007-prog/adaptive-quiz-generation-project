import { useEffect, useRef } from 'react'

const media = (q) => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(q).matches
export const prefersReducedMotion = () => media('(prefers-reduced-motion: reduce)')
const finePointer = () => media('(hover: hover) and (pointer: fine)')

/** Reveals every [data-reveal] element inside `rootRef` once it scrolls into view.
 *  Without IntersectionObserver (tests, old browsers) or with reduced motion, everything is shown at once. */
export function useReveal(rootRef) {
  useEffect(() => {
    const root = rootRef.current
    if (!root) return undefined
    const items = [...root.querySelectorAll('[data-reveal]')]
    if (prefersReducedMotion() || typeof IntersectionObserver === 'undefined') {
      items.forEach((el) => el.classList.add('is-in'))
      return undefined
    }
    root.classList.add('reveal-on')
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target) }
      })
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 })
    items.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [rootRef])
}

/** Moves the element a little against the scroll direction. Transform only, no layout work. */
export function useParallax(ref, factor = 0.06, max = 40) {
  useEffect(() => {
    const el = ref.current
    if (!el || prefersReducedMotion()) return undefined
    let frame = 0
    const update = () => {
      frame = 0
      const r = el.parentElement.getBoundingClientRect()
      const fromCentre = r.top + r.height / 2 - window.innerHeight / 2
      const y = Math.max(-max, Math.min(max, -fromCentre * factor))
      el.style.setProperty('--parallax', `${y.toFixed(1)}px`)
    }
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update) }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [ref, factor, max])
}

/** A card that tilts gently toward the pointer and settles back when it leaves.
 *  Only on devices with a fine pointer, never with reduced motion. */
export function Tilt({ as: Tag = 'div', max = 5, className = '', children, ...rest }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !finePointer() || prefersReducedMotion()) return undefined
    el.classList.add('tilt-on')
    let frame = 0
    let next = null
    const apply = () => {
      frame = 0
      if (!next) return
      el.style.setProperty('--rx', `${next.rx.toFixed(2)}deg`)
      el.style.setProperty('--ry', `${next.ry.toFixed(2)}deg`)
    }
    const onMove = (e) => {
      const r = el.getBoundingClientRect()
      const px = (e.clientX - r.left) / r.width - 0.5
      const py = (e.clientY - r.top) / r.height - 0.5
      next = { rx: -py * max * 2, ry: px * max * 2 }
      el.classList.add('is-tilting')
      if (!frame) frame = requestAnimationFrame(apply)
    }
    const onLeave = () => {
      next = { rx: 0, ry: 0 }
      el.classList.remove('is-tilting')
      if (!frame) frame = requestAnimationFrame(apply)
    }
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerleave', onLeave)
    return () => {
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerleave', onLeave)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [max])
  return <Tag ref={ref} className={`tilt ${className}`} {...rest}>{children}</Tag>
}
