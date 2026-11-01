import { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import Button from './Button'

/** Native <dialog> modal: focus trap, Esc to close and backdrop come from the browser. */
export default function Dialog({ open, onClose, title, description, children, footer, wide }) {
  const ref = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog ref={ref} className={`dialog ${wide ? 'dialog--wide' : ''}`} onClose={onClose} aria-labelledby={titleId}
      onClick={(e) => { if (e.target === ref.current) onClose?.() }}>
      {open && (
        <>
          <div className="dialog__head">
            <div>
              <h2 id={titleId} style={{ fontSize: 'var(--fs-lg)' }}>{title}</h2>
              {description && <p className="muted" style={{ fontSize: 'var(--fs-sm)', marginTop: 4 }}>{description}</p>}
            </div>
            <Button variant="ghost" size="sm" icon={X} aria-label="Close" onClick={onClose} />
          </div>
          <div className="dialog__body">{children}</div>
          {footer && <div className="dialog__foot">{footer}</div>}
        </>
      )}
    </dialog>
  )
}

export function ConfirmDialog({ open, onClose, onConfirm, title, children, confirmLabel = 'Confirm', tone = 'primary', loading }) {
  return (
    <Dialog open={open} onClose={onClose} title={title}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant={tone} onClick={onConfirm} loading={loading}>{confirmLabel}</Button>
      </>}>
      {children}
    </Dialog>
  )
}
