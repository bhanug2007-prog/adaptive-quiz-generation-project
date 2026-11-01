import { useEffect, useRef } from 'react'
import {
  BufferAttribute, BufferGeometry, Color, Group, LineBasicMaterial, LineSegments, PerspectiveCamera,
  Points, PointsMaterial, Scene, Vector3, WebGLRenderer,
} from 'three'

/* Plain three.js (no React Three Fiber): keeps the lazily loaded chunk to three itself,
   so nothing the rest of the app needs is pulled into it. */

/* Reads a CSS custom property so the scene uses the design tokens, not raw colours. */
function token(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

/* Points spread evenly over a sphere (Fibonacci lattice), linked to near neighbours:
   a quiet "knowledge graph" behind the quiz cards. */
function buildGraph(count = 150, radius = 2.3, linkDist = 0.62) {
  const pts = []
  const golden = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2
    const r = Math.sqrt(1 - y * y)
    const t = golden * i
    pts.push(new Vector3(Math.cos(t) * r * radius, y * radius, Math.sin(t) * r * radius))
  }
  const pos = new Float32Array(count * 3)
  pts.forEach((p, i) => p.toArray(pos, i * 3))
  const seg = []
  for (let i = 0; i < count; i++) {
    for (let j = i + 1; j < count; j++) {
      if (pts[i].distanceTo(pts[j]) < linkDist) seg.push(...pts[i].toArray(), ...pts[j].toArray())
    }
  }
  return { pos, seg: new Float32Array(seg) }
}

/** The only WebGL on the site. Loaded lazily; the render loop stops while `active` is false. */
export default function HeroCanvas({ active, pointer }) {
  const hostRef = useRef(null)
  const ctl = useRef(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return undefined
    let renderer
    try {
      renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' })
    } catch {
      return undefined // WebGL failed after all: the CSS composition stays on its own
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
    renderer.setClearColor(0x000000, 0)
    const canvas = renderer.domElement
    canvas.className = 'lp-hero__canvas'
    canvas.setAttribute('aria-hidden', 'true')
    host.appendChild(canvas)

    const scene = new Scene()
    const camera = new PerspectiveCamera(45, 1, 0.1, 50)
    camera.position.set(0, 0, 6.2)

    const { pos, seg } = buildGraph()
    const group = new Group()
    group.rotation.x = 0.25
    const pGeo = new BufferGeometry()
    pGeo.setAttribute('position', new BufferAttribute(pos, 3))
    const pMat = new PointsMaterial({ color: new Color(token('--accent', '#9485ff')), size: 0.045, transparent: true, opacity: 0.75, depthWrite: false })
    const lGeo = new BufferGeometry()
    lGeo.setAttribute('position', new BufferAttribute(seg, 3))
    const lMat = new LineBasicMaterial({ color: new Color(token('--teal', '#49d6c5')), transparent: true, opacity: 0.2, depthWrite: false })
    group.add(new Points(pGeo, pMat), new LineSegments(lGeo, lMat))
    scene.add(group)

    const resize = () => {
      const w = host.clientWidth || 1
      const h = host.clientHeight || 1
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.render(scene, camera)
    }
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
    ro?.observe(host)
    resize()

    let raf = 0
    let last = 0
    const frame = (t) => {
      const dt = Math.min((t - (last || t)) / 1000, 0.05)
      last = t
      const p = pointer.current
      const k = Math.min(1, dt * 2)
      group.rotation.y += dt * 0.06
      group.rotation.x += (0.25 + p.y * 0.18 - group.rotation.x) * k
      group.rotation.z += (-p.x * 0.08 - group.rotation.z) * k
      renderer.render(scene, camera)
      raf = requestAnimationFrame(frame)
    }
    ctl.current = {
      start() { if (!raf) { last = 0; raf = requestAnimationFrame(frame) } },
      stop() { cancelAnimationFrame(raf); raf = 0 },
    }

    return () => {
      ctl.current?.stop()
      ctl.current = null
      ro?.disconnect()
      pGeo.dispose(); pMat.dispose(); lGeo.dispose(); lMat.dispose()
      renderer.dispose()
      canvas.remove()
    }
  }, [pointer])

  useEffect(() => {
    if (active) ctl.current?.start()
    else ctl.current?.stop()
  }, [active])

  return <div ref={hostRef} className="lp-hero__canvas-host" aria-hidden="true" />
}
