import { LABELS } from '../../utils/format'

/** Coloured dot + label for a mastery label key. */
export function MasteryChip({ label, showText = true }) {
  const l = LABELS[label] || LABELS.not_attempted
  return (
    <span className="mastery-chip" style={{ '--chip-color': l.color }} title={l.text}>
      <span className="dot" aria-hidden="true" />
      {showText ? l.text : <span className="visually-hidden">{l.text}</span>}
    </span>
  )
}

/** Three bars showing how much evidence an estimate rests on (low / moderate / high). */
export function EvidenceMeter({ level }) {
  const text = { low: 'Low evidence', moderate: 'Moderate evidence', high: 'High evidence', none: 'No evidence' }[level] || 'No evidence'
  return (
    <span className="row" style={{ gap: 6 }} title={text}>
      <span className="evidence" data-level={level} aria-hidden="true"><i /><i /><i /></span>
      <span className="visually-hidden">{text}</span>
    </span>
  )
}

/** Circular score ring. value 0..1 (or null for no data). */
export function MasteryRing({ value, size = 96, stroke = 8, color = 'var(--teal)', caption, label }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const v = value == null ? 0 : Math.max(0, Math.min(1, value))
  return (
    <div className="ring" style={{ width: size, height: size, '--ring-color': color }} role="img"
      aria-label={label || (value == null ? 'No data' : `${Math.round(v * 100)} percent`)}>
      <svg width={size} height={size} aria-hidden="true">
        <circle className="ring__track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} />
        <circle className="ring__value" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - v)} />
      </svg>
      <span className="ring__label" aria-hidden="true">
        <span className="ring__num" style={{ fontSize: size > 80 ? 'var(--fs-xl)' : 'var(--fs-sm)' }}>
          {value == null ? '—' : `${Math.round(v * 100)}%`}
        </span>
        {caption && <span className="ring__cap">{caption}</span>}
      </span>
    </div>
  )
}
