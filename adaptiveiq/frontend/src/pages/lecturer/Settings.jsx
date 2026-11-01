import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CheckCircle2, KeyRound, Link2, MailWarning, Unlink, User } from 'lucide-react'
import { authApi, lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { useAuth } from '../../auth/AuthProvider'
import { Alert, Badge, Button, Card, ConfirmDialog, Field, Input, LoadingBlock, PageHeader, useToast } from '../../components/ui'
import { date } from '../../utils/format'
import { passwordProblem } from '../auth/Register'
import { errText } from '../../components/lecturer/util'

export default function Settings() {
  const [sp] = useSearchParams()
  const google = sp.get('google')
  return (
    <div className="lc-page">
      <PageHeader eyebrow="Settings" title="Settings" subtitle="Your profile, password and connected services." />
      {google === 'connected' && <Alert tone="success">Google account connected.</Alert>}
      {google === 'failed' && <Alert tone="error">Google did not finish connecting. Try again, and allow the requested access.</Alert>}
      <div className="lc-settings">
        <Profile />
        <Password />
        <Google />
      </div>
    </div>
  )
}

function Profile() {
  const { user, setUser } = useAuth()
  const { notify } = useToast()
  const [v, setV] = useState({ full_name: user?.full_name || '', department: user?.department || '', designation: user?.designation || '' })
  const [busy, setBusy] = useState(false)
  const [resending, setResending] = useState(false)
  const [error, setError] = useState(null)
  const nameProblem = v.full_name.trim().length < 2 ? 'Enter your name.' : null
  const save = async (e) => {
    e.preventDefault()
    if (nameProblem) return setError(nameProblem)
    setBusy(true)
    setError(null)
    try {
      const u = await authApi.updateMe({ full_name: v.full_name.trim(), department: v.department.trim() || null, designation: v.designation.trim() || null })
      setUser(u)
      notify('Profile saved')
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
    return undefined
  }
  const resend = async () => {
    setResending(true)
    try { await authApi.resendVerification(); notify('Verification email sent. Check your inbox and spam folder.') } catch (err) { notify(errText(err), 'error') } finally { setResending(false) }
  }
  return (
    <Card title={<span className="row" style={{ gap: 8 }}><User size={16} aria-hidden="true" />Profile</span>}>
      <form className="stack" onSubmit={save} noValidate>
        <div className="lc-email-row">
          <div>
            <p className="lc-mini-label">Email</p>
            <p>{user?.email}</p>
          </div>
          {user?.email_verified
            ? <Badge tone="success" icon={CheckCircle2}>Verified</Badge>
            : <Badge tone="warning" icon={MailWarning}>Not verified</Badge>}
        </div>
        {!user?.email_verified && (
          <Alert tone="warning" action={<Button size="sm" onClick={resend} loading={resending}>Resend link</Button>}>
            {user?.verification_required ? 'Verify your email to publish quizzes, generate questions and enrol students.' : 'Your email is not verified yet.'}
          </Alert>
        )}
        <Field label="Full name" error={error === nameProblem ? nameProblem : undefined}>{(a) => <Input {...a} autoComplete="name" value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} maxLength={120} />}</Field>
        <Field label="Department (optional)">{(a) => <Input {...a} value={v.department} onChange={(e) => setV({ ...v, department: e.target.value })} maxLength={120} />}</Field>
        <Field label="Designation (optional)">{(a) => <Input {...a} value={v.designation} onChange={(e) => setV({ ...v, designation: e.target.value })} maxLength={120} placeholder="Assistant Professor" />}</Field>
        {error && error !== nameProblem && <Alert tone="error">{error}</Alert>}
        <p className="faint lc-small">Lecturer account since {date(user?.created_at)}.</p>
        <div className="row" style={{ justifyContent: 'flex-end' }}><Button type="submit" variant="primary" loading={busy}>Save profile</Button></div>
      </form>
    </Card>
  )
}

function Password() {
  const { notify } = useToast()
  const [v, setV] = useState({ current: '', next: '', confirm: '' })
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const p = {
    current: !v.current ? 'Enter your current password.' : null,
    next: passwordProblem(v.next),
    confirm: v.confirm !== v.next ? 'The passwords do not match.' : null,
  }
  const show = touched ? p : {}
  const submit = async (e) => {
    e.preventDefault()
    setTouched(true)
    setError(null)
    if (p.current || p.next || p.confirm) return
    setBusy(true)
    try {
      await authApi.changePassword(v.current, v.next)
      notify('Password changed')
      setV({ current: '', next: '', confirm: '' })
      setTouched(false)
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title={<span className="row" style={{ gap: 8 }}><KeyRound size={16} aria-hidden="true" />Change password</span>}>
      <form className="stack" onSubmit={submit} noValidate>
        <Field label="Current password" error={show.current}>{(a) => <Input {...a} type="password" autoComplete="current-password" value={v.current} onChange={(e) => setV({ ...v, current: e.target.value })} />}</Field>
        <Field label="New password" hint="At least 8 characters, with a letter and a number." error={show.next}>{(a) => <Input {...a} type="password" autoComplete="new-password" value={v.next} onChange={(e) => setV({ ...v, next: e.target.value })} />}</Field>
        <Field label="Confirm new password" error={show.confirm}>{(a) => <Input {...a} type="password" autoComplete="new-password" value={v.confirm} onChange={(e) => setV({ ...v, confirm: e.target.value })} />}</Field>
        {error && <Alert tone="error">{error}</Alert>}
        <div className="row" style={{ justifyContent: 'flex-end' }}><Button type="submit" variant="primary" loading={busy}>Change password</Button></div>
      </form>
    </Card>
  )
}

function Google() {
  const s = useApi(() => lecturerApi.googleStatus(), [])
  const { notify } = useToast()
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [error, setError] = useState(null)
  const connect = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await lecturerApi.googleConnect()
      window.location.assign(r.auth_url)
    } catch (err) {
      setError(errText(err))
      setBusy(false)
    }
  }
  const disconnect = async () => {
    setBusy(true)
    try { await lecturerApi.googleDisconnect(); notify('Google account disconnected'); setConfirm(false); s.reload() } catch (err) { notify(errText(err), 'error') } finally { setBusy(false) }
  }
  const d = s.data
  return (
    <Card title={<span className="row" style={{ gap: 8 }}><Link2 size={16} aria-hidden="true" />Google Forms</span>}
      subtitle="Lets you turn a fully approved quiz into a Google Form in your own Google account.">
      {s.loading && <LoadingBlock rows={1} label="Checking Google connection" />}
      {s.error && <Alert tone="error" action={<Button size="sm" onClick={s.reload}>Retry</Button>}>{errText(s.error)}</Alert>}
      {d && (
        <div className="stack">
          <dl className="lc-dl">
            <div><dt>Set up on this server</dt><dd>{d.configured ? 'Yes' : 'No'}</dd></div>
            <div><dt>Your Google account</dt><dd>{d.connected ? <Badge tone="success">Connected</Badge> : <Badge>Not connected</Badge>}</dd></div>
            <div><dt>Tested against Google</dt><dd>{d.tested_against_google ? 'Yes' : 'Not yet'}</dd></div>
          </dl>
          {!d.tested_against_google && <Alert tone="warning">This integration has not been tested against the live Google Forms API yet. Check every form it creates before sharing it.</Alert>}
          {!d.configured && <Alert tone="info">{d.message || 'Google Forms export is not set up on this server.'} Each quiz's Reports & export tab has a manual export you can paste into a form instead.</Alert>}
          {error && <Alert tone="error">{error}</Alert>}
          {d.configured && (d.connected
            ? <div><Button variant="danger" icon={Unlink} onClick={() => setConfirm(true)}>Disconnect Google</Button></div>
            : <div><Button variant="primary" icon={Link2} onClick={connect} loading={busy}>Connect Google account</Button></div>)}
        </div>
      )}
      <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} onConfirm={disconnect} loading={busy} tone="danger" confirmLabel="Disconnect" title="Disconnect Google?">
        <p className="muted">AdaptiveIQ forgets the stored access. Forms you already created stay in your Google Drive.</p>
      </ConfirmDialog>
    </Card>
  )
}
