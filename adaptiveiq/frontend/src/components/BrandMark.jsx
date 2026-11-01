import { Link } from 'react-router-dom'

/** The AdaptiveIQ mark: a quiz sheet with two answered (ticked) questions on a navy tile.
 *  Fixed colours so the mark looks the same on the light landing page, the dark portal and the favicon. */
export function LogoMark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="#1b2a52" />
      <rect x="8.5" y="6" width="15" height="20" rx="2.5" fill="#ffffff" />
      <path d="M11.2 12.1l1.6 1.6 2.9-3.2" fill="none" stroke="#4f55c9" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="17.4" y="11.3" width="3.9" height="1.7" rx="0.85" fill="#c3c7e6" />
      <path d="M11.2 19.1l1.6 1.6 2.9-3.2" fill="none" stroke="#4f55c9" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="17.4" y="18.3" width="3.9" height="1.7" rx="0.85" fill="#c3c7e6" />
    </svg>
  )
}

export default function BrandMark({ to = '/', compact }) {
  return (
    <Link to={to} className="brand" aria-label="AdaptiveIQ home">
      <LogoMark />
      {!compact && <span className="brand__word">Adaptive<span>IQ</span></span>}
    </Link>
  )
}
