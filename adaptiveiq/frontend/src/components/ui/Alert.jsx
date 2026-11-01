import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'

const ICONS = { info: Info, success: CheckCircle2, warning: AlertTriangle, error: XCircle }

export default function Alert({ tone = 'info', title, children, action }) {
  const Icon = ICONS[tone]
  return (
    <div className={`alert alert--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon size={16} aria-hidden="true" />
      <div style={{ flex: 1, minWidth: 0 }}>
        {title && <strong style={{ display: 'block', marginBottom: 2 }}>{title}</strong>}
        {children}
      </div>
      {action}
    </div>
  )
}
