import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, UserPlus } from 'lucide-react'
import { Alert, Button, Field, Input, Segmented } from '../../components/ui'
import { useApi } from '../../api/useApi'
import { authApi } from '../../api/endpoints'
import { homeFor, useAuth } from '../../auth/AuthProvider'
import AuthShell from './AuthShell'

/** Same rules as backend/app/schemas/auth.py check_password. */
export function passwordProblem(p) {
  if (!p || p.length < 8) return 'Use at least 8 characters.'
  if (new TextEncoder().encode(p).length > 72) return 'Use at most 72 bytes.'
  if (!/[A-Za-z]/.test(p) || !/\d/.test(p)) return 'Include at least one letter and one number.'
  return null
}

export default function Register() {
  const { user, register: signUp } = useAuth()
  const navigate = useNavigate()
  const cfg = useApi(() => authApi.config(), [])
  const [role, setRole] = useState('student')
  const [error, setError] = useState(null)
  const [show, setShow] = useState(false)
  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm({
    defaultValues: { full_name: '', email: '', password: '', confirm: '', invite_code: '', roll_number: '', program: '', semester: '', department: '' },
  })

  if (user) return <Navigate to={homeFor(user)} replace />

  const domains = cfg.data?.allowed_email_domains || []
  const lecturerOk = cfg.data?.lecturer_signup_enabled

  const onSubmit = async (v) => {
    setError(null)
    const body = { email: v.email.trim(), password: v.password, full_name: v.full_name.trim(), role }
    if (role === 'student') {
      if (v.roll_number.trim()) body.roll_number = v.roll_number.trim()
      if (v.program.trim()) body.program = v.program.trim()
      if (v.semester) body.semester = Number(v.semester)
    } else {
      body.invite_code = v.invite_code.trim()
      if (v.department.trim()) body.department = v.department.trim()
    }
    try {
      const u = await signUp(body)
      navigate(homeFor(u), { replace: true })
    } catch (e) {
      setError(e.message)
    }
  }

  const emailRule = (val) => {
    const e = val.trim().toLowerCase()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) return 'Enter a valid email address.'
    if (domains.length && !domains.includes(e.split('@').pop())) return `Use an email ending in ${domains.map((d) => `@${d}`).join(', ')}.`
    return true
  }

  return (
    <AuthShell title="Create your account" subtitle="Sign up with your email and a password.">
      <form className="stack" onSubmit={handleSubmit(onSubmit)} noValidate>
        {error && <Alert tone="error">{error}</Alert>}
        <div className="field">
          <span className="field__label" id="role-label">I am a</span>
          <Segmented name="role" label="Account type" value={role} onChange={setRole}
            options={[{ value: 'student', label: 'Student' }, { value: 'lecturer', label: 'Lecturer' }]} />
        </div>
        {role === 'lecturer' && cfg.data && !lecturerOk && (
          <Alert tone="warning">Lecturer sign-up is turned off on this server. Ask the administrator for an account.</Alert>
        )}
        <Field label="Full name" error={errors.full_name?.message}>
          {(a) => <Input {...a} autoComplete="name" {...register('full_name', { validate: (x) => x.trim().length >= 2 || 'Enter your name.' })} />}
        </Field>
        <Field label="Email" error={errors.email?.message}
          hint={domains.length ? `Only ${domains.map((d) => `@${d}`).join(', ')} addresses can register.` : undefined}>
          {(a) => <Input {...a} type="email" autoComplete="email" placeholder="you@example.com" {...register('email', { validate: emailRule })} />}
        </Field>
        <Field label="Password" error={errors.password?.message} hint="At least 8 characters, with a letter and a number.">
          {(a) => (
            <div className="input-affix">
              <Input {...a} type={show ? 'text' : 'password'} autoComplete="new-password"
                {...register('password', { validate: (p) => passwordProblem(p) || true })} />
              <button type="button" className="input-affix__btn" onClick={() => setShow((s) => !s)}
                aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}>
                {show ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
              </button>
            </div>
          )}
        </Field>
        <Field label="Confirm password" error={errors.confirm?.message}>
          {(a) => <Input {...a} type={show ? 'text' : 'password'} autoComplete="new-password"
            {...register('confirm', { validate: (c) => c === watch('password') || 'The passwords do not match.' })} />}
        </Field>

        {role === 'student' ? (
          <div className="grid-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 150px), 1fr))' }}>
            <Field label="Roll number (optional)">{(a) => <Input {...a} {...register('roll_number')} />}</Field>
            <Field label="Semester (optional)" error={errors.semester?.message}>
              {(a) => <Input {...a} type="number" min={1} max={12} inputMode="numeric"
                {...register('semester', { validate: (s) => !s || (Number(s) >= 1 && Number(s) <= 12) || 'Between 1 and 12.' })} />}
            </Field>
            <Field label="Program (optional)" className="span-all">{(a) => <Input {...a} placeholder="B.Tech DSAI" {...register('program')} />}</Field>
          </div>
        ) : (
          <>
            <Field label="Lecturer invite code" error={errors.invite_code?.message} hint="Given to you by the administrator.">
              {(a) => <Input {...a} autoComplete="off" {...register('invite_code', { validate: (x) => role !== 'lecturer' || x.trim().length > 0 || 'Enter the invite code.' })} />}
            </Field>
            <Field label="Department (optional)">{(a) => <Input {...a} {...register('department')} />}</Field>
          </>
        )}

        <Button type="submit" variant="primary" block icon={UserPlus} loading={isSubmitting}
          disabled={role === 'lecturer' && cfg.data && !lecturerOk}>Create account</Button>
        <p className="muted" style={{ fontSize: 'var(--fs-sm)', textAlign: 'center' }}>
          Already have an account? <Link to="/signin" className="link">Sign in</Link>
        </p>
      </form>
    </AuthShell>
  )
}
