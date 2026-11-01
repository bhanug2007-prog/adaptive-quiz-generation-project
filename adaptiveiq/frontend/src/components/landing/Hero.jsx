import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { ArrowRight, Sparkles } from 'lucide-react'
import { Button } from '../ui'
import HeroCards from './HeroCards'
import { shouldUseWebGL, useInView, usePageVisible, useReducedMotion } from './motion'

const HeroCanvas = lazy(() => import('./HeroCanvas'))

/** Smoothly eases the composition toward the pointer. Writes CSS variables directly (no re-render). */
function usePointerTilt(enabled, stageRef, pointer) {
  useEffect(() => {
    const stage = stageRef.current
    if (!enabled || !stage) return undefined
    if (!window.matchMedia?.('(pointer: fine)').matches) return undefined
    const target = { x: 0, y: 0 }
    const cur = { x: 0, y: 0 }
    let raf = 0
    const tick = () => {
      cur.x += (target.x - cur.x) * 0.08
      cur.y += (target.y - cur.y) * 0.08
      stage.style.setProperty('--lp-tx', cur.x.toFixed(4))
      stage.style.setProperty('--lp-ty', cur.y.toFixed(4))
      pointer.current.x = cur.x
      pointer.current.y = cur.y
      raf = Math.abs(target.x - cur.x) + Math.abs(target.y - cur.y) > 0.001 ? requestAnimationFrame(tick) : 0
    }
    const onMove = (e) => {
      if (e.pointerType && e.pointerType !== 'mouse') return
      target.x = Math.max(-1, Math.min(1, (e.clientX / window.innerWidth) * 2 - 1))
      target.y = Math.max(-1, Math.min(1, (e.clientY / window.innerHeight) * 2 - 1))
      if (!raf) raf = requestAnimationFrame(tick)
    }
    const onLeave = () => {
      target.x = 0
      target.y = 0
      if (!raf) raf = requestAnimationFrame(tick)
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    document.documentElement.addEventListener('pointerleave', onLeave)
    return () => {
      window.removeEventListener('pointermove', onMove)
      document.documentElement.removeEventListener('pointerleave', onLeave)
      cancelAnimationFrame(raf)
    }
  }, [enabled, stageRef, pointer])
}

export default function Hero() {
  const reduced = useReducedMotion()
  const pageVisible = usePageVisible()
  const [heroRef, heroInView] = useInView({ rootMargin: '80px' })
  const stageRef = useRef(null)
  const pointer = useRef({ x: 0, y: 0 })
  const [webgl, setWebgl] = useState(false)

  // Decide after first paint so the text and cards never wait for WebGL.
  useEffect(() => {
    if (!shouldUseWebGL(reduced)) {
      setWebgl(false)
      return undefined
    }
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 200))
    const cancel = window.cancelIdleCallback || clearTimeout
    const id = idle(() => setWebgl(true))
    return () => cancel(id)
  }, [reduced])

  usePointerTilt(!reduced && heroInView, stageRef, pointer)
  const animating = !reduced && heroInView && pageVisible

  return (
    <section ref={heroRef} className={`lp-hero ${animating ? '' : 'is-paused'}`} aria-labelledby="lp-hero-title">
      <div className="lp-hero__glow" aria-hidden="true" />
      <div className="lp-hero__grid" aria-hidden="true" />
      <div className="container lp-hero__inner">
        <div className="lp-hero__copy">
          <p className="lp-badge"><Sparkles size={13} aria-hidden="true" />AI-POWERED ADAPTIVE LEARNING</p>
          <h1 id="lp-hero-title" className="lp-hero__title">
            Every learner is different. <span>Their learning should be too.</span>
          </h1>
          <p className="lp-hero__sub">
            Generate intelligent quizzes, uncover learning gaps, and turn assessment results into personalized
            learning journeys — all in one AI-powered platform.
          </p>
          <div className="lp-hero__ctas">
            <Button variant="primary" size="lg" to="/register" iconRight={ArrowRight}>Start Learning</Button>
            <Button size="lg" href="#lecturers">Explore Lecturer Tools</Button>
          </div>
          <ul className="lp-hero__facts" aria-label="At a glance">
            <li>Every AI question is checked automatically</li>
            <li>Lecturers approve before publishing</li>
            <li>Mastery shown with its evidence</li>
          </ul>
        </div>

        <div className="lp-hero__visual">
          <div className="lp-hero__scene" aria-hidden="true">
            {webgl && (
              <Suspense fallback={null}>
                <HeroCanvas active={animating} pointer={pointer} />
              </Suspense>
            )}
          </div>
          <HeroCards ref={stageRef} />
        </div>
      </div>
    </section>
  )
}
