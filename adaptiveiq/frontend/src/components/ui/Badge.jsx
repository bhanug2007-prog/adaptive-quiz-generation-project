export default function Badge({ tone, icon: Icon, children, className = '', ...rest }) {
  return (
    <span className={['badge', tone && `badge--${tone}`, className].filter(Boolean).join(' ')} {...rest}>
      {Icon && <Icon size={12} aria-hidden="true" />}
      {children}
    </span>
  )
}
