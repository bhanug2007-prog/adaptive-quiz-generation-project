import { useInView } from './motion'

/**
 * Fades and lifts its children in the first time they scroll into view.
 * Content is always in the DOM; with reduced motion the CSS shows it immediately.
 */
export default function Reveal({ as: Tag = 'div', delay = 0, className = '', children, ...rest }) {
  const [ref, inView] = useInView({ once: true, rootMargin: '0px 0px -8% 0px' })
  return (
    <Tag ref={ref} className={`lp-reveal ${inView ? 'is-in' : ''} ${className}`.trim()}
      style={delay ? { '--lp-delay': `${delay}ms` } : undefined} {...rest}>
      {children}
    </Tag>
  )
}

/** Section heading block used by every landing section. */
export function SectionHead({ eyebrow, title, lead, id, align = 'left' }) {
  return (
    <Reveal className={`lp-head lp-head--${align}`}>
      {eyebrow && <p className="lp-eyebrow">{eyebrow}</p>}
      <h2 id={id} className="lp-h2">{title}</h2>
      {lead && <p className="lp-lead">{lead}</p>}
    </Reveal>
  )
}
