import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Alert, Button, LoadingBlock } from '../../components/ui'
import { authApi } from '../../api/endpoints'
import { homeFor, useAuth } from '../../auth/AuthProvider'
import AuthShell from './AuthShell'

export default function VerifyEmail() {
  const [params] = useSearchParams()
  const { user, setUser } = useAuth()
  const [state, setState] = useState({ status: 'working', error: null, verified: null })
  const sent = useRef(false)
  const token = params.get('token')

  useEffect(() => {
    if (sent.current) return
    sent.current = true
    if (!token) { setState({ status: 'error', error: 'This link has no verification code in it.' }); return }
    authApi.verifyEmail(token)
      .then((u) => {
        setState({ status: 'done', error: null, verified: u })
        setUser((cur) => (cur && cur.id === u.id ? u : cur))
      })
      .catch((e) => setState({ status: 'error', error: e.message }))
  }, [token, setUser])

  return (
    <AuthShell title="Verify your email">
      {state.status === 'working' && <LoadingBlock rows={1} label="Checking your link" />}
      {state.status === 'done' && (
        <div className="stack">
          <Alert tone="success" title="Email verified">{state.verified.email} is verified.</Alert>
          <Button variant="primary" to={user ? homeFor(user) : '/signin'}>{user ? 'Continue to your portal' : 'Sign in'}</Button>
        </div>
      )}
      {state.status === 'error' && (
        <div className="stack">
          <Alert tone="error">{state.error}</Alert>
          <Button to={user ? homeFor(user) : '/signin'}>{user ? 'Back to your portal' : 'Sign in to get a new link'}</Button>
        </div>
      )}
    </AuthShell>
  )
}
