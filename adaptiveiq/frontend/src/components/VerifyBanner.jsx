import { useState } from 'react'
import { MailWarning } from 'lucide-react'
import { Button } from './ui'
import { authApi } from '../api/endpoints'
import { useAuth } from '../auth/AuthProvider'

/** Shown in the portal until the email address is verified. Important actions stay locked until then. */
export default function VerifyBanner() {
  const { user } = useAuth()
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  if (!user || user.email_verified) return null
  const resend = async () => {
    setBusy(true)
    try {
      await authApi.resendVerification()
      setMsg(`A new link was sent to ${user.email}.`)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }
  const locked = user.role === 'lecturer'
    ? 'creating courses, generating and publishing quizzes, and enrolling students'
    : 'joining courses and generating practice quizzes'
  return (
    <div className="verify-banner" role="status">
      <MailWarning size={18} aria-hidden="true" />
      <p>
        Verify your email to unlock {locked}. Open the link we sent to <strong>{user.email}</strong>.
        {msg && <span className="verify-banner__msg"> {msg}</span>}
      </p>
      <Button size="sm" onClick={resend} loading={busy}>Send a new link</Button>
    </div>
  )
}
