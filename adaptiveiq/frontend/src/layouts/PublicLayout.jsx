import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import BrandMark from '../components/BrandMark'
import { homeFor, useAuth } from '../auth/AuthProvider'

const LINKS = [
  ['#product', 'Product'],
  ['#features', 'Features'],
  ['#experience', 'Lecturers & Students'],
  ['#how', 'How It Works'],
]

export default function PublicLayout() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const loc = useLocation()

  useEffect(() => { setOpen(false) }, [loc.pathname, loc.hash])
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const cta = user
    ? <Link className="s-btn s-btn--primary s-btn--sm" to={homeFor(user)}>Open portal</Link>
    : <Link className="s-btn s-btn--primary s-btn--sm" to="/register">Get Started</Link>

  return (
    <div className="site">
      <a className="skip-link" href="#main">Skip to content</a>
      <header className={`site-nav ${scrolled || open ? 'is-scrolled' : ''}`}>
        <div className="s-wrap site-nav__inner">
          <BrandMark />
          <nav aria-label="Main" className="site-nav__links">
            {LINKS.map(([href, label]) => <a key={href} href={`/${href}`}>{label}</a>)}
          </nav>
          <div className="site-nav__end">
            {!user && <Link className="site-nav__signin" to="/signin">Sign in</Link>}
            {cta}
            <button type="button" className="site-nav__menu" aria-label={open ? 'Close menu' : 'Open menu'}
              aria-expanded={open} aria-controls="site-menu" onClick={() => setOpen((o) => !o)}>
              {open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
            </button>
          </div>
        </div>
        {open && (
          <nav id="site-menu" className="site-drawer" aria-label="Main">
            <div className="s-wrap">
              {LINKS.map(([href, label]) => <a key={href} href={`/${href}`} onClick={() => setOpen(false)}>{label}</a>)}
              {!user && <Link to="/signin">Sign in</Link>}
            </div>
          </nav>
        )}
      </header>
      <main id="main" tabIndex={-1} style={{ outline: 'none' }}>
        <Outlet />
      </main>
      <footer className="site-foot">
        <div className="s-wrap site-foot__inner">
          <div className="site-foot__brand">
            <BrandMark />
            <p>Quiz generation, topic mastery and adaptive practice for students and lecturers.</p>
            <p className="site-foot__credit">A DSAI team project at IIIT Dharwad.</p>
          </div>
          <nav aria-label="Footer" className="site-foot__cols">
            <div>
              <p className="site-foot__title">Product</p>
              {LINKS.map(([href, label]) => <a key={href} href={`/${href}`}>{label}</a>)}
            </div>
            <div>
              <p className="site-foot__title">Account</p>
              <Link to="/register">Create an account</Link>
              <Link to="/signin">Sign in</Link>
            </div>
          </nav>
        </div>
        <div className="s-wrap site-foot__base">
          <p>© 2026 AdaptiveIQ</p>
          <p>Previews on this page use sample data.</p>
        </div>
      </footer>
    </div>
  )
}
