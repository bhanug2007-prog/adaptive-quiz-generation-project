export default function Card({ title, subtitle, actions, as: Tag = 'section', variant, interactive, className = '', children, ...rest }) {
  const cls = ['card', variant && `card--${variant}`, interactive && 'card--interactive', className].filter(Boolean).join(' ')
  return (
    <Tag className={cls} {...rest}>
      {(title || actions) && (
        <div className="card__head">
          <div>
            {title && <h2 className="card__title">{title}</h2>}
            {subtitle && <p className="card__sub">{subtitle}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </Tag>
  )
}
