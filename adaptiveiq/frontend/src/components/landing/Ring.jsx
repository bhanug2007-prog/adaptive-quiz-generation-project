import { useInView } from './motion'

/**
 * Mastery ring that draws itself when it first scrolls into view.
 * value: 0..100, or null for "insufficient evidence".
 */
export default function Ring({ value, size = 72, stroke = 6, color = 'var(--teal)', label, caption }) {
  const [ref, inView] = useInView({ once: true })
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const v = value == null ? 0 : Math.max(0, Math.min(100, value))
  const offset = inView ? c * (1 - v / 100) : c
  return (
    <div ref={ref} className="lp-ring" style={{ width: size, height: size, '--lp-ring': color }} role="img"
      aria-label={label || (value == null ? 'Insufficient evidence' : `${v} out of 100`)}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle className="lp-ring__track" cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} fill="none" />
        <circle className="lp-ring__value" cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} fill="none"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset} />
      </svg>
      <span className="lp-ring__label" aria-hidden="true">
        <span className="lp-ring__num" style={{ fontSize: size >= 88 ? 'var(--fs-xl)' : size >= 64 ? 'var(--fs-md)' : 'var(--fs-xs)' }}>
          {value == null ? '–' : v}
        </span>
        {caption && <span className="lp-ring__cap">{caption}</span>}
      </span>
    </div>
  )
}
