import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { CheckCircle2, Info, XCircle } from 'lucide-react'

const ToastCtx = createContext({ notify: () => {} })
const ICON = { success: CheckCircle2, error: XCircle, info: Info }

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const notify = useCallback((message, tone = 'success') => {
    const id = Math.random().toString(36).slice(2)
    setItems((xs) => [...xs.slice(-3), { id, message, tone }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === 'error' ? 7000 : 4000)
  }, [])
  const value = useMemo(() => ({ notify }), [notify])
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="toasts" aria-live="polite" aria-atomic="false">
        {items.map((t) => {
          const Icon = ICON[t.tone] || Info
          return (
            <div key={t.id} className={`toast toast--${t.tone}`} role={t.tone === 'error' ? 'alert' : 'status'}>
              <Icon size={16} aria-hidden="true" />
              <span>{t.message}</span>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
