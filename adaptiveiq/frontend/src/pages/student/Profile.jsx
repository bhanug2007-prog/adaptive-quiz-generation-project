import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { BadgeCheck, Eye, EyeOff, KeyRound, MailWarning, Save } from 'lucide-react'
import { Alert, Badge, Button, Card, Field, Input, PageHeader, useToast } from '../../components/ui'
import { authApi } from '../../api/endpoints'
import { useAuth } from '../../auth/AuthProvider'
import { date } from '../../utils/format'
import { passwordProblem } from '../auth/Register'

function ProfileForm({ user, onSaved }) {
  const [error, setError] = useState(null)
  const { register, handleSubmit, formState: { errors, isSubmitting, isDirty }, reset } = useForm({
    defaultValues: {
      full_name: user.full_name || '', roll_number: user.roll_number || '', program: user.program || '',
      semester: user.semester ?? '', weekly_study_hours: user.weekly_study_hours ?? '',
    },
  })
  const onSubmit = async (v) => {
    setError(null)
    const body = {
      full_name: v.full_name.trim(), roll_number: v.roll_number.trim() || null, program: v.program.trim() || null,
      semester: v.semester === '' ? null : Number(v.semester), weekly_study_hours: v.weekly_study_hours === '' ? null : Number(v.weekly_study_hours),
    }
    try {
      const u = await authApi.updateMe(body)
      onSaved(u)
      reset({ full_name: u.full_name || '', roll_number: u.roll_number || '', program: u.program || '', semester: u.semester ?? '', weekly_study_hours: u.weekly_study_hours ?? '' })
    } catch (e) {
      setError(e.message)
    }
  }
  const intRule = (min, max, what) => (val) => {
    if (val === '' || val == null) return true
    const n = Number(val)
    return (Number.isInteger(n) && n >= min && n <= max) || `${what} must be a whole number from ${min} to ${max}.`
  }
  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="stack-lg">
      <div className="st-form-grid">
        <Field label="Full name" error={errors.full_name?.message} className="span-all">
          {(p) => <Input {...p} autoComplete="name" {...register('full_name', {
            validate: (v) => (v.trim().length >= 2 && v.trim().length <= 120) || 'Enter your name (2 to 120 characters).',
          })} />}
        </Field>
        <Field label="Roll number" error={errors.roll_number?.message}>
          {(p) => <Input {...p} {...register('roll_number', { maxLength: { value: 40, message: 'At most 40 characters.' } })} />}
        </Field>
        <Field label="Program" hint="For example B.Tech DSAI" error={errors.program?.message}>
          {(p) => <Input {...p} {...register('program', { maxLength: { value: 120, message: 'At most 120 characters.' } })} />}
        </Field>
        <Field label="Semester" error={errors.semester?.message}>
          {(p) => <Input {...p} type="number" inputMode="numeric" min={1} max={12} {...register('semester', { validate: intRule(1, 12, 'Semester') })} />}
        </Field>
        <Field label="Weekly study hours" hint="Used to split your study plan between topics." error={errors.weekly_study_hours?.message}>
          {(p) => <Input {...p} type="number" inputMode="numeric" min={0} max={80} {...register('weekly_study_hours', { validate: intRule(0, 80, 'Study hours') })} />}
        </Field>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <div><Button type="submit" variant="teal" icon={Save} loading={isSubmitting} disabled={!isDirty}>Save changes</Button></div>
    </form>
  )
}

function PasswordForm() {
  const [error, setError] = useState(null)
  const [show, setShow] = useState(false)
  const { notify } = useToast()
  const { register, handleSubmit, watch, reset, formState: { errors, isSubmitting } } = useForm({ defaultValues: { current: '', next: '', confirm: '' } })
  const onSubmit = async (v) => {
    setError(null)
    try {
      await authApi.changePassword(v.current, v.next)
      reset()
      notify('Password changed.')
    } catch (e) {
      setError(e.message)
    }
  }
  const type = show ? 'text' : 'password'
  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="stack-lg">
      <Field label="Current password" error={errors.current?.message}>
        {(p) => <Input {...p} type={type} autoComplete="current-password" {...register('current', { required: 'Enter your current password.' })} />}
      </Field>
      <div className="st-form-grid">
        <Field label="New password" hint="At least 8 characters, with a letter and a number." error={errors.next?.message}>
          {(p) => (
            <div className="input-affix">
              <Input {...p} type={type} autoComplete="new-password" {...register('next', {
                validate: (val) => passwordProblem(val) || (val === watch('current') ? 'Choose a password different from the current one.' : true),
              })} />
              <button type="button" className="input-affix__btn" onClick={() => setShow((s) => !s)} aria-label={show ? 'Hide passwords' : 'Show passwords'}>
                {show ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
              </button>
            </div>
          )}
        </Field>
        <Field label="Confirm new password" error={errors.confirm?.message}>
          {(p) => <Input {...p} type={type} autoComplete="new-password" {...register('confirm', { validate: (val) => val === watch('next') || 'The passwords do not match.' })} />}
        </Field>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <div><Button type="submit" variant="secondary" icon={KeyRound} loading={isSubmitting}>Change password</Button></div>
    </form>
  )
}

export default function Profile() {
  const { user, setUser } = useAuth()
  const { notify } = useToast()
  const [resend, setResend] = useState({ busy: false, msg: null })
  if (!user) return null
  const sendAgain = async () => {
    setResend({ busy: true, msg: null })
    try { await authApi.resendVerification(); setResend({ busy: false, msg: `A new link was sent to ${user.email}.` }) } catch (e) { setResend({ busy: false, msg: e.message }) }
  }
  return (
    <div className="st-page st-narrow stack-lg">
      <PageHeader title="Profile" subtitle="Your account details and password." />
      <Card title="Account">
        <dl className="st-account">
          <div><dt>Email</dt><dd>{user.email}</dd></div>
          <div>
            <dt>Email status</dt>
            <dd>
              {user.email_verified
                ? <Badge tone="success" icon={BadgeCheck}>Verified</Badge>
                : <span className="row" style={{ gap: 8 }}><Badge tone="warning" icon={MailWarning}>Not verified</Badge>
                  <Button size="sm" variant="ghost" onClick={sendAgain} loading={resend.busy}>Send the link again</Button></span>}
              {resend.msg && <p className="faint st-small" role="status">{resend.msg}</p>}
            </dd>
          </div>
          <div><dt>Role</dt><dd>Student</dd></div>
          <div><dt>Member since</dt><dd>{date(user.created_at)}</dd></div>
        </dl>
      </Card>
      <Card title="Profile details">
        <ProfileForm user={user} onSaved={(u) => { setUser(u); notify('Profile saved.') }} />
      </Card>
      <Card title="Change password">
        <PasswordForm />
      </Card>
    </div>
  )
}
