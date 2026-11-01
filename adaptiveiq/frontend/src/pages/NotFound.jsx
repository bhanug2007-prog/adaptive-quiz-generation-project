import { Compass } from 'lucide-react'
import { Button, EmptyState } from '../components/ui'
import { homeFor, useAuth } from '../auth/AuthProvider'

export default function NotFound() {
  const { user } = useAuth()
  return (
    <div style={{ padding: 'var(--space-8) 0' }}>
      <EmptyState icon={Compass} title="Page not found" action={<Button variant="primary" to={user ? homeFor(user) : '/'}>Go home</Button>}>
        The page you asked for does not exist, or you do not have access to it.
      </EmptyState>
    </div>
  )
}
