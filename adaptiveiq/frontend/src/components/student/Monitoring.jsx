import { Camera, Eye, Maximize, Mic, MonitorUp, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Alert, Button, Card } from '../ui'
import { eventLine } from '../../monitoring/labels'

/** What a monitored assessment records, in plain words. `m` is the quiz's monitoring settings. */
export function monitoringLines(m) {
  if (!m) return []
  const out = []
  if (m.tab) out.push({ icon: Eye, key: 'tab', text: 'When you leave the quiz page (another tab, another window or minimising) and for how long. Not which site or app you opened.' })
  if (m.fullscreen === 'required') out.push({ icon: Maximize, key: 'fs', text: 'Full screen is required. Leaving it is recorded and the questions are hidden until you return.' })
  if (m.fullscreen === 'record') out.push({ icon: Maximize, key: 'fs', text: 'When you leave full screen.' })
  if (m.camera) out.push({ icon: Camera, key: 'cam', text: 'Your camera is checked every few seconds, in this browser only, for whether no face or more than one face is visible. No picture or video is saved or sent. It does not recognise who you are.' })
  if (m.microphone) out.push({ icon: Mic, key: 'mic', text: 'Your microphone level is checked in this browser for speech-like sound and how long it lasts. No audio is recorded, saved or sent, and nothing is transcribed.' })
  return out
}

export function MonitoringNotice({ m, retentionDays, children }) {
  const lines = monitoringLines(m)
  if (!lines.length) return null
  return (
    <Card title="This assessment is monitored" variant="flat">
      <div className="stack" style={{ gap: 'var(--space-3)' }}>
        <p className="st-small">Your lecturer turned on monitoring for this assessment, to help keep it fair. It records:</p>
        <ul className="st-rules">
          {lines.map((l) => <li key={l.key}><l.icon size={15} aria-hidden="true" />{l.text}</li>)}
        </ul>
        <p className="st-small muted">
          Only these events and their times are stored, with your attempt. Your lecturer sees them as "Normal", "Event recorded" or
          "Needs review" and decides what, if anything, they mean: an event is not an accusation. You can see everything recorded
          about you after the quiz.{retentionDays ? ` The events are deleted after ${retentionDays} days.` : ''}
        </p>
        <p className="st-small muted">
          Confirmed activity alerts appear during the quiz. At the configured alert threshold, lecturer review is required;
          you can continue answering and your marks are not changed by alerts.
        </p>
        <p className="st-small muted">
          If you cannot use a camera or microphone, or do not want to, do not start: contact your lecturer about another way to
          take this assessment.
        </p>
        {children}
      </div>
    </Card>
  )
}

const DEVICE_TEXT = { on: 'on', off: 'off', denied: 'not allowed', unavailable: 'not available', lost: 'stopped' }

/** Shown before the questions each time a monitored attempt is opened (it needs a click to start the camera). */
export function MonitoringGate({ attempt, mon }) {
  const m = attempt.monitoring
  return (
    <div className="st-page st-narrow stack-lg">
      <MonitoringNotice m={m} retentionDays={m.retention_days}>
        <p className="st-small">
          Press the button to turn monitoring on and see the questions. Your browser will ask for permission
          {m.camera && m.microphone ? ' to use the camera and microphone' : m.camera ? ' to use the camera' : m.microphone ? ' to use the microphone' : ''}.
          If you say no, you can still answer, and your lecturer will see that permission was not given.
        </p>
        {attempt.deadline_at && <Alert tone="info">Your time limit is already running.</Alert>}
        {mon.notice && <Alert tone="warning">{mon.notice}</Alert>}
        <ActivityWarnings mon={mon} />
        <div className="row">
          <Button variant="teal" size="lg" icon={ShieldCheck} onClick={mon.start} loading={mon.starting}>Turn on monitoring and continue</Button>
        </div>
      </MonitoringNotice>
    </div>
  )
}

/** Small status pills in the quiz header, so monitoring is never hidden from the student. */
export function MonitoringStatus({ mon }) {
  if (!mon.enabled || !mon.started) return null
  const { cfg, devices } = mon
  return (
    <div className="st-monbar" role="status" aria-label="Monitoring status">
      <span className="st-monpill"><ShieldCheck size={13} aria-hidden="true" />Monitored</span>
      {mon.record?.warning_count != null && <span className="st-monpill">Alerts: {mon.record.warning_count} / {mon.record.warning_threshold}</span>}
      {cfg.camera && <span className="st-monpill" data-state={devices.camera}><Camera size={13} aria-hidden="true" />Camera {DEVICE_TEXT[devices.camera] || devices.camera}</span>}
      {cfg.microphone && <span className="st-monpill" data-state={devices.microphone}><Mic size={13} aria-hidden="true" />Microphone {DEVICE_TEXT[devices.microphone] || devices.microphone}</span>}
    </div>
  )
}

export function MonitoringMessages({ mon }) {
  if (!mon.enabled || !mon.started) return null
  return (
    <>
      <ActivityWarnings mon={mon} />
      {mon.notice && (
        <Alert tone="warning" title="Recorded">
          {mon.notice} <button type="button" className="st-save__retry" onClick={mon.clearNotice}>Dismiss</button>
        </Alert>
      )}
      {mon.faceHint === 'face_none' && <Alert tone="info">The camera cannot see a face. Check the light and that you are in view.</Alert>}
      {mon.faceHint === 'face_multiple' && <Alert tone="info">The camera sees more than one face.</Alert>}
    </>
  )
}

export function ActivityWarnings({ mon }) {
  const [open, setOpen] = useState(false)
  const [category, setCategory] = useState('false_alert')
  const [note, setNote] = useState('')
  const [eventSeq, setEventSeq] = useState('')
  const [reportId, setReportId] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  if (!mon.enabled) return null
  const r = mon.record
  const history = r?.warning_history || []
  const last = history.at(-1)
  const send = async (e) => {
    e.preventDefault()
    setBusy(true)
    setMessage('')
    const id = reportId || crypto.randomUUID()
    setReportId(id)
    try {
      await mon.reportProblem({ report_id: id, category, note, event_seq: eventSeq === '' ? null : Number(eventSeq) })
      setMessage('Report saved for your lecturer. The original event remains recorded.')
      setOpen(false); setNote(''); setReportId(null)
    } catch { setMessage('Could not save your report. Please retry when connected.') }
    finally { setBusy(false) }
  }
  return <div className="stack" style={{ gap: 8 }}>
    {last && <div className="st-activity-warning" role="alert" aria-atomic="true">
      <strong>Activity warning {r.warning_count} of {r.warning_threshold}: {eventLine(last)}</strong>
      <p>{r.review_required
        ? 'Lecturer review required. You can continue answering. This alert does not submit your quiz or change your marks.'
        : 'Please check your surroundings and return to the quiz. This event has been recorded.'}</p>
      <p>Activity signals can be caused by lighting, background sound, or device problems. Your lecturer will review the context.</p>
    </div>}
    {mon.syncError && <Alert tone="warning">Monitoring sync pending. The alert count shows the last server-confirmed total. You can continue answering.</Alert>}
    {!!history.length && <details><summary>Warning history ({history.length})</summary>
      <ol>{history.map((e) => <li key={e.seq}>{new Date(e.at).toLocaleString()} · {eventLine(e)}</li>)}</ol>
    </details>}
    <div><button type="button" className="st-save__retry" onClick={() => setOpen(!open)} aria-expanded={open}>Report a false alert or device problem</button></div>
    {open && <form onSubmit={send} className="stack">
      <label>Report type <select value={category} onChange={(e) => setCategory(e.target.value)} disabled={busy}>
        <option value="false_alert">False alert</option><option value="device_problem">Device problem</option>
      </select></label>
      <label>Related warning <select value={eventSeq} onChange={(e) => setEventSeq(e.target.value)} disabled={busy}>
        <option value="">General device or monitoring problem</option>
        {history.map((e) => <option key={e.seq} value={e.seq}>{new Date(e.at).toLocaleTimeString()} · {eventLine(e)}</option>)}
      </select></label>
      <label>Details (optional)<textarea maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} disabled={busy} /></label>
      <p className="st-small">Only your authorized lecturer can review this report. It does not remove the event.</p>
      <Button type="submit" loading={busy}>Send report</Button>
    </form>}
    {message && <p role="status">{message}</p>}
  </div>
}

export function FullscreenRequired({ mon }) {
  return (
    <Card>
      <div className="stack" style={{ alignItems: 'center', textAlign: 'center', padding: 'var(--space-6) 0' }}>
        <MonitorUp size={28} aria-hidden="true" />
        <h2 className="st-h2">This assessment needs full screen</h2>
        <p className="muted st-small">The questions are hidden until you return to full screen. Your timer keeps running and your answers are saved.</p>
        <Button variant="teal" icon={Maximize} onClick={mon.enterFullscreen}>Return to full screen</Button>
      </div>
    </Card>
  )
}

/** After the quiz: everything that was recorded about this attempt, so monitoring is never a secret. */
export function MyMonitoringRecord({ record }) {
  if (!record) return null
  const shown = (record.events || []).filter((e) => e.kind !== 'page_hidden')
  return (
    <Card title="What was recorded during this attempt" subtitle="Monitoring events your lecturer can see. They are signals to review, not a judgement.">
      {shown.length ? (
        <ol className="list-plain stack" style={{ gap: 6 }}>
          {shown.map((e) => (
            <li key={e.seq} className="st-small"><span className="faint num">{new Date(e.at).toLocaleTimeString()}</span> · {eventLine(e)}</li>
          ))}
        </ol>
      ) : <p className="muted st-small">Nothing was recorded.</p>}
    </Card>
  )
}
