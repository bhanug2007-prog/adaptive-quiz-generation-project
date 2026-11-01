import { useId, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { ChevronDown } from 'lucide-react'

/** A disclosure button with a calm height animation (instant with reduced motion). */
export default function Expandable({ label, openLabel, children, defaultOpen = false, className = '' }) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  const reduce = useReducedMotion()
  return (
    <div className={`st-expand ${className}`} data-open={open || undefined}>
      <button type="button" className="st-expand__btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        <ChevronDown size={16} aria-hidden="true" className="st-expand__chev" />
        {open && openLabel ? openLabel : label}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div id={id} key="body" className="st-expand__body"
            initial={reduce ? false : { height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={reduce ? { opacity: 0, transition: { duration: 0 } } : { height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.2, 0.7, 0.2, 1] }}>
            <div className="st-expand__inner">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
