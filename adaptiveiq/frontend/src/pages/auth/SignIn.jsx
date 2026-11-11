import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Eye, EyeOff, LogIn } from 'lucide-react'
import { Alert, Button, Field, Input } from '../../components/ui'
import { homeFor, useAuth } from '../../auth/AuthProvider'
import AuthShell from './AuthShell'

/** Only same-app paths are allowed as a redirect target. */
export function safeNext(next, user) {
  if (!next || !next.startsWith('/') || next.startsWith('//')) return homeFor(user)
  if (!next.startsWith(`/${user.role}`)) return homeFor(user)
  return next
}

export default function SignIn() {
  const { user, login } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const [show, setShow] = useState(false)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({ defaultValues: { email: '', password: '' } })

  if (user) return <Navigate to={safeNext(params.get('next'), user)} replace />

  const onSubmit = async ({ email, password }) => {
    setError(null)
    try {
      const u = await login(email.trim(), password)
      navigate(safeNext(params.get('next'), u), { replace: true })
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <AuthShell title="Sign in" subtitle="Use the email and password you registered with.">
      <form className="stack" onSubmit={handleSubmit(onSubmit)} noValidate>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Email" error={errors.email?.message}>
          {(a) => <Input {...a} type="email" autoComplete="email" placeholder="you@example.com"
            {...register('email', { required: 'Enter your email.', pattern: { value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: 'Enter a valid email address.' } })} />}
        </Field>
        <Field label="Password" error={errors.password?.message}>
          {(a) => (
            <div className="input-affix">
              <Input {...a} type={show ? 'text' : 'password'} autoComplete="current-password"
                {...register('password', { required: 'Enter your password.' })} />
              <button type="button" className="input-affix__btn" onClick={() => setShow((s) => !s)}
                aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}>
                {show ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
              </button>
            </div>
          )}
        </Field>
        <Button type="submit" variant="primary" block icon={LogIn} loading={isSubmitting}>Sign in</Button>
        <p className="muted" style={{ fontSize: 'var(--fs-sm)', textAlign: 'center' }}>
          <Link to="/forgot-password" className="link">Forgot password?</Link>
        </p>
        <p className="muted" style={{ fontSize: 'var(--fs-sm)', textAlign: 'center' }}>
          New to AdaptiveIQ? <Link to="/register" className="link">Create an account</Link>
        </p>
      </form>
    </AuthShell>
  )
}
