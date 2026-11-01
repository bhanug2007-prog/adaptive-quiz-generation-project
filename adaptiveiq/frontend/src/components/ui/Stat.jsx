export default function Stat({ label, value, hint, icon: Icon, tone }) {
  return (
    <div className="stat">
      <span className="stat__label">{Icon && <Icon size={14} aria-hidden="true" style={{ color: tone ? `var(--${tone})` : undefined }} />}{label}</span>
      <span className="stat__value">{value ?? '—'}</span>
      {hint && <span className="stat__hint">{hint}</span>}
    </div>
  )
}
