export default function ProgressBar({ value, max = 100, label, tone }) {
  const pct = max ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  return (
    <div className={`progress ${tone ? `progress--${tone}` : ''}`} role="progressbar" aria-label={label}
      aria-valuemin={0} aria-valuemax={max} aria-valuenow={Math.round(value)}>
      <div className="progress__bar" style={{ width: `${pct}%` }} />
    </div>
  )
}
