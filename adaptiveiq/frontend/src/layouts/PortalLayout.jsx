import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { LogOut, Menu, X } from 'lucide-react'
import BrandMark from '../components/BrandMark'
import ModelStatus from '../components/ModelStatus'
import VerifyBanner from '../components/VerifyBanner'
import { Button } from '../components/ui'
import { useAuth } from '../auth/AuthProvider'
import { LECTURER_NAV, STUDENT_NAV } from './nav'

export default function PortalLayout({ role }) {
  const { user, logout } = useAuth()
  const nav = role === 'lecturer' ? LECTURER_NAV : STUDENT_NAV
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const navigate = useNavigate()
  useEffect(() => { setOpen(false) }, [loc.pathname])
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])
  const signOut = async () => { await logout(); navigate('/') }
  const initials = (user?.full_name || '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <div className="portal" data-open={open || undefined}>
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className="portal__side" aria-label={`${role === 'lecturer' ? 'Lecturer' : 'Student'} navigation`}>
        <div className="portal__brand">
          <BrandMark to={role === 'lecturer' ? '/lecturer' : '/student'} />
          <Button className="portal__close" variant="ghost" size="sm" icon={X} aria-label="Close menu" onClick={() => setOpen(false)} />
        </div>
        <p className="portal__role eyebrow">{role === 'lecturer' ? 'Lecturer portal' : 'Student portal'}</p>
        <nav>
          <ul className="portal__nav">
            {nav.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} className="portal__link">
                  <Icon size={17} aria-hidden="true" />
                  <span>{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="portal__user">
          <span className="avatar" aria-hidden="true">{initials}</span>
          <div className="portal__who">
            <strong>{user?.full_name}</strong>
            <span>{user?.email}</span>
          </div>
          <Button variant="ghost" size="sm" icon={LogOut} aria-label="Sign out" title="Sign out" onClick={signOut} />
        </div>
      </aside>
      <div className="portal__scrim" onClick={() => setOpen(false)} aria-hidden="true" />
      <div className="portal__main">
        <header className="portal__top">
          <Button className="portal__menu" variant="ghost" size="sm" icon={Menu} aria-label="Open menu" aria-expanded={open} onClick={() => setOpen(true)} />
          <div className="portal__top-brand"><BrandMark compact to={role === 'lecturer' ? '/lecturer' : '/student'} /></div>
          <div style={{ flex: 1 }} />
          <ModelStatus />
        </header>
        <main id="main" className="portal__content" tabIndex={-1}>
          <VerifyBanner />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
