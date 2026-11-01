import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { LoadingBlock } from '../components/ui'
import { homeFor, useAuth } from './AuthProvider'

/** Route guard for convenience only; the backend enforces every permission. */
export default function RequireRole({ role }) {
  const { user, checking } = useAuth()
  const loc = useLocation()
  if (checking) return <div className="container" style={{ paddingTop: '4rem' }}><LoadingBlock /></div>
  if (!user) return <Navigate to={`/signin?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  if (role && user.role !== role) return <Navigate to={homeFor(user)} replace />
  return <Outlet />
}
