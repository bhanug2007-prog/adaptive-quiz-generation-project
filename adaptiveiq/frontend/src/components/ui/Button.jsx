import { forwardRef } from 'react'
import { Link } from 'react-router-dom'

/** variant: primary | secondary | teal | ghost | danger; size: sm | md | lg. Pass `to` for a router link. */
const Button = forwardRef(function Button(
  { variant = 'secondary', size = 'md', block, icon: Icon, iconRight: IconRight, loading, to, href, className = '', children, disabled, type = 'button', ...rest },
  ref,
) {
  const cls = ['btn', variant !== 'secondary' && `btn--${variant}`, size !== 'md' && `btn--${size}`, block && 'btn--block',
    !children && 'btn--icon', className].filter(Boolean).join(' ')
  const inner = (
    <>
      {loading ? <span className="spinner" aria-hidden="true" /> : Icon && <Icon size={size === 'sm' ? 14 : 16} aria-hidden="true" />}
      {children}
      {IconRight && <IconRight size={size === 'sm' ? 14 : 16} aria-hidden="true" />}
    </>
  )
  if (to) return <Link ref={ref} to={to} className={cls} {...rest}>{inner}</Link>
  if (href) return <a ref={ref} href={href} className={cls} {...rest}>{inner}</a>
  return (
    <button ref={ref} type={type} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {inner}
    </button>
  )
})

export default Button
