import { AlertTriangle, Inbox } from 'lucide-react'
import Button from './Button'

export function Skeleton({ height = 16, width = '100%', style }) {
  return <div className="skeleton" style={{ height, width, ...style }} aria-hidden="true" />
}

export function LoadingBlock({ rows = 3, label = 'Loading' }) {
  return (
    <div className="stack" role="status" aria-live="polite">
      <span className="visually-hidden">{label}…</span>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} height={i === 0 ? 28 : 64} width={i === 0 ? '40%' : '100%'} />)}
    </div>
  )
}

export function EmptyState({ icon: Icon = Inbox, title, children, action }) {
  return (
    <div className="state">
      <div className="state__icon"><Icon size={22} aria-hidden="true" /></div>
      <h3 className="state__title">{title}</h3>
      {children && <p className="state__text">{children}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry, title = 'Something went wrong' }) {
  return (
    <div className="state" role="alert">
      <div className="state__icon" style={{ color: 'var(--error)' }}><AlertTriangle size={22} aria-hidden="true" /></div>
      <h3 className="state__title">{title}</h3>
      <p className="state__text">{error?.message || String(error || 'Unknown error')}</p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  )
}
