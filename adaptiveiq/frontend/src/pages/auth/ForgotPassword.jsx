import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { Mail } from 'lucide-react'
import { Alert, Button, Field, Input } from '../../components/ui'
import { authApi } from '../../api/endpoints'
import AuthShell from './AuthShell'

const GENERIC_SENT_MESSAGE = 'If an account with that email exists, we sent a password reset link.'

export default function ForgotPassword() {
  const [status, setStatus] = useState('idle') // idle | success
  const [serverMessage, setServerMessage] = useState(GENERIC_SENT_MESSAGE)
  const [error, setError] = useState(null)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({ defaultValues: { email: '' } })

  const onSubmit = async ({ email }) => {
    setError(null)
    try {
      const res = await authApi.forgotPassword(email.trim())
      setServerMessage(res?.message || GENERIC_SENT_MESSAGE)
      setStatus('success')
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <AuthShell
      title="Forgot your password?"
      subtitle="Enter the email address for your student or lecturer account and we will send a reset link."
    >
      {status === 'success' ? (
        <div className="stack">
          <Alert tone="success" title="Check your email">
            {serverMessage} Reset links expire after 15 minutes and can only be used once.
          </Alert>
          <Button variant="primary" to="/signin">Back to sign in</Button>
          <Button variant="secondary" onClick={() => setStatus('idle')}>Send another link</Button>
        </div>
      ) : (
        <form className="stack" onSubmit={handleSubmit(onSubmit)} noValidate>
          {error && <Alert tone="error">{error}</Alert>}
          <Field label="Email" error={errors.email?.message}>
            {(a) => (
              <Input
                {...a}
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                {...register('email', {
                  required: 'Enter your email.',
                  pattern: { value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: 'Enter a valid email address.' },
                })}
              />
            )}
          </Field>
          <Button type="submit" variant="primary" block icon={Mail} loading={isSubmitting}>
            Send reset link
          </Button>
          <p className="muted" style={{ fontSize: 'var(--fs-sm)', textAlign: 'center' }}>
            Remembered your password? <Link to="/signin" className="link">Sign in</Link>
          </p>
        </form>
      )}
    </AuthShell>
  )
}
