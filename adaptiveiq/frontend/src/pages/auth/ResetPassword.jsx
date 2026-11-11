import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useSearchParams } from 'react-router-dom'
import { Eye, EyeOff, KeyRound } from 'lucide-react'
import { Alert, Button, Field, Input, LoadingBlock } from '../../components/ui'
import { authApi } from '../../api/endpoints'
import { useAuth } from '../../auth/AuthProvider'
import AuthShell from './AuthShell'
import { passwordProblem } from './Register'

function classifyTokenError(message) {
  const lower = (message || '').toLowerCase()
  if (lower.includes('expired') && !lower.includes('invalid')) return 'expired-token'
  return 'invalid-token'
}

export default function ResetPassword() {
  const [params] = useSearchParams()
  const { setUser } = useAuth()
  // Hold the token only in component/router memory; never persist reset tokens to browser storage.
  const token = params.get('token') || ''

  const [stage, setStage] = useState(token ? 'loading' : 'invalid-token')
  const [stageError, setStageError] = useState(token ? null : 'This password reset link is missing its token.')
  const [submitError, setSubmitError] = useState(null)
  const [show, setShow] = useState(false)

  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm({
    defaultValues: { new_password: '', confirm: '' },
  })

  useEffect(() => {
    if (!token) {
      setStage('invalid-token')
      setStageError('This password reset link is missing its token.')
      return
    }
    let cancelled = false
    setStage('loading')
    setStageError(null)
    authApi.verifyResetToken(token)
      .then(() => {
        if (!cancelled) setStage('ready')
      })
      .catch((e) => {
        if (cancelled) return
        setStage(classifyTokenError(e.message))
        setStageError(e.message)
      })
    return () => { cancelled = true }
  }, [token])

  const onSubmit = async ({ new_password }) => {
    setSubmitError(null)
    try {
      await authApi.resetPassword(token, new_password)
      setUser(null)
      setStage('success')
    } catch (e) {
      if (e.status === 400) {
        setStage(classifyTokenError(e.message))
        setStageError(e.message)
      } else {
        setSubmitError(e.message)
      }
    }
  }

  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Set a new password for your AdaptiveIQ account. Earlier sessions will be signed out."
    >
      {stage === 'loading' && <LoadingBlock rows={2} label="Checking your reset link" />}

      {stage === 'expired-token' && (
        <div className="stack">
          <Alert tone="warning" title="Reset link expired">
            {stageError || 'This password reset link has expired. Request a new one.'}
          </Alert>
          <Button variant="primary" to="/forgot-password">Request a new reset link</Button>
          <p className="muted" style={{ fontSize: 'var(--fs-sm)', textAlign: 'center' }}>
            <Link to="/signin" className="link">Back to sign in</Link>
          </p>
        </div>
      )}

      {stage === 'invalid-token' && (
        <div className="stack">
          <Alert tone="error" title="Reset link not valid">
            {stageError || 'This password reset link is invalid or has already been used.'}
          </Alert>
          <Button variant="primary" to="/forgot-password">Request a new reset link</Button>
          <p className="muted" style={{ fontSize: 'var(--fs-sm)', textAlign: 'center' }}>
            <Link to="/signin" className="link">Back to sign in</Link>
          </p>
        </div>
      )}

      {stage === 'ready' && (
        <form className="stack" onSubmit={handleSubmit(onSubmit)} noValidate>
          {submitError && <Alert tone="error">{submitError}</Alert>}
          <Field
            label="New password"
            error={errors.new_password?.message}
            hint="At least 8 characters, with a letter and a number."
          >
            {(a) => (
              <div className="input-affix">
                <Input
                  {...a}
                  type={show ? 'text' : 'password'}
                  autoComplete="new-password"
                  {...register('new_password', { validate: (p) => passwordProblem(p) || true })}
                />
                <button
                  type="button"
                  className="input-affix__btn"
                  onClick={() => setShow((s) => !s)}
                  aria-label={show ? 'Hide password' : 'Show password'}
                  aria-pressed={show}
                >
                  {show ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                </button>
              </div>
            )}
          </Field>
          <Field label="Confirm new password" error={errors.confirm?.message}>
            {(a) => (
              <Input
                {...a}
                type={show ? 'text' : 'password'}
                autoComplete="new-password"
                {...register('confirm', { validate: (c) => c === watch('new_password') || 'The passwords do not match.' })}
              />
            )}
          </Field>
          <Button type="submit" variant="primary" block icon={KeyRound} loading={isSubmitting}>
            Reset password
          </Button>
          <p className="muted" style={{ fontSize: 'var(--fs-sm)', textAlign: 'center' }}>
            <Link to="/signin" className="link">Back to sign in</Link>
          </p>
        </form>
      )}

      {stage === 'success' && (
        <div className="stack">
          <Alert tone="success" title="Password reset complete">
            Your password has been updated and all previous sessions have been signed out.
          </Alert>
          <Button variant="primary" to="/signin">Sign in</Button>
        </div>
      )}
    </AuthShell>
  )
}
