import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ClipboardCopy, Download, ExternalLink, FileText, ShieldCheck } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Badge, Button, Card, LoadingBlock, Textarea, useToast } from '../ui'
import { dateTime } from '../../utils/format'
import { copyText, errText, slug } from './util'

export const QUIZ_REPORTS = [
  { key: 'results', label: 'Results', desc: 'Each student’s attempts: raw score, percentage, late penalty and contribution earned.', fn: lecturerApi.downloadQuizResults },
  { key: 'completion', label: 'Completion', desc: 'Every enrolled student and whether they submitted.', fn: lecturerApi.downloadQuizCompletion },
  { key: 'questions', label: 'Question analysis', desc: 'Per question: answers, % correct, % incorrect, % skipped and flags.', fn: lecturerApi.downloadQuizQuestions },
]

export function CsvButtons({ quiz }) {
  const { notify } = useToast()
  const [busy, setBusy] = useState(null)
  const get = async (r) => {
    setBusy(r.key)
    try {
      await r.fn(quiz.id, `${slug(quiz.title)}-${r.key}.csv`)
      notify(`${r.label} CSV downloaded`)
    } catch (e) {
      notify(errText(e), 'error')
    } finally {
      setBusy(null)
    }
  }
  return (
    <ul className="list-plain lc-reports">
      {QUIZ_REPORTS.map((r) => (
        <li key={r.key}>
          <div><strong>{r.label}</strong><p className="faint lc-small">{r.desc}</p></div>
          <Button size="sm" icon={Download} onClick={() => get(r)} loading={busy === r.key} aria-label={`Download ${r.label} CSV for ${quiz.title}`}>CSV</Button>
        </li>
      ))}
    </ul>
  )
}

function ManualExport({ quiz, allApproved }) {
  const [text, setText] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const { notify } = useToast()
  const load = async () => {
    setBusy(true)
    setError(null)
    try { setText(await lecturerApi.manualExport(quiz.id)) } catch (e) { setError(errText(e)) } finally { setBusy(false) }
  }
  const copy = async () => notify((await copyText(text)) ? 'Copied to the clipboard' : 'Could not copy. Select the text and copy it by hand.', 'info')
  return (
    <Card title="Manual export" subtitle="Plain text with questions, options, answer key and explanations, to paste into Google Forms or another LMS by hand. It includes the answer key, so do not share it with students.">
      {!allApproved && <Alert tone="info">Approve every question first; the export only includes a fully reviewed quiz.</Alert>}
      {text == null ? (
        <Button icon={FileText} onClick={load} loading={busy} disabled={!allApproved}>Show export text</Button>
      ) : (
        <div className="stack">
          <Textarea aria-label="Export text" readOnly rows={12} value={text} className="lc-mono" />
          <div className="row"><Button icon={ClipboardCopy} onClick={copy}>Copy to clipboard</Button><Button variant="ghost" onClick={load} loading={busy}>Refresh</Button></div>
        </div>
      )}
      {error && <Alert tone="error">{error}</Alert>}
    </Card>
  )
}

function GoogleForms({ quiz, allApproved }) {
  const status = useApi(() => lecturerApi.googleStatus(), [])
  const exports = useApi(() => lecturerApi.googleExports(quiz.id), [quiz.id])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await lecturerApi.googleForm(quiz.id)
      setResult(r)
      exports.reload()
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }
  const s = status.data
  return (
    <Card title="Google Forms" subtitle="Creates a Google Form from the approved questions in your Google account. The AdaptiveIQ quiz and its results stay separate from the form.">
      {status.loading && <LoadingBlock rows={1} label="Checking Google connection" />}
      {status.error && <Alert tone="error">{errText(status.error)}</Alert>}
      {s && (
        <div className="stack">
          <Alert tone="warning">This integration has not been tested against Google yet. Check the created form before sharing it, or use the manual export.</Alert>
          {!s.configured ? (
            <Alert tone="info" title="Not set up on this server">
              {s.message || 'Google Forms export is not configured.'} See <Link className="link" to="/lecturer/settings">Settings</Link> for the connection status.
            </Alert>
          ) : !s.connected ? (
            <Alert tone="info" title="Google account not connected">Connect your Google account in <Link className="link" to="/lecturer/settings">Settings</Link>, then come back.</Alert>
          ) : (
            <div className="row">
              <Button variant="primary" onClick={create} loading={busy} disabled={!allApproved}>Create Google Form</Button>
              {!allApproved && <span className="faint lc-small">Approve every question first.</span>}
            </div>
          )}
          {error && <Alert tone="error" title="The form was not created">{error}</Alert>}
          {result && (
            <Alert tone={result.status === 'created' ? 'success' : 'warning'} title={result.status === 'created' ? 'Form created' : `Export ${result.status}`}>
              {result.error && <p>{result.error}</p>}
              {result.edit_url && <p><a className="link" href={result.edit_url} target="_blank" rel="noreferrer">Open the form to check it <ExternalLink size={12} aria-hidden="true" style={{ display: 'inline' }} /></a></p>}
            </Alert>
          )}
          {exports.data?.length > 0 && (
            <div>
              <p className="lc-mini-label">Previous exports</p>
              <ul className="list-plain">
                {exports.data.map((x, i) => (
                  <li key={i} className="row lc-small">
                    <Badge tone={x.status === 'created' ? 'success' : x.status === 'failed' ? 'error' : 'warning'}>{x.status}</Badge>
                    <span className="faint">{dateTime(x.created_at)}</span>
                    {x.edit_url && <a className="link" href={x.edit_url} target="_blank" rel="noreferrer">Edit form</a>}
                    {x.responder_url && <a className="link" href={x.responder_url} target="_blank" rel="noreferrer">Student link</a>}
                    {x.error && <span className="muted">{x.error}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

export default function QuizExport({ quiz, goTo }) {
  const allApproved = quiz.question_count > 0 && (quiz.review_counts?.approved || 0) === quiz.question_count
  return (
    <div className="stack-lg">
      <Card title="Monitoring & assessment activity"
        subtitle="Tab/window leaves, camera face checks, microphone audio activity, device permission status, and manual review notes.">
        <div className="row-between" style={{ flexWrap: 'wrap', gap: 12 }}>
          <p className="muted lc-small">
            Inspect student-wise monitoring counts, chronological event timelines, and record manual review outcomes.
          </p>
          {goTo ? (
            <Button icon={ShieldCheck} variant="secondary" onClick={() => goTo('monitoring')}>
              Open monitoring &amp; activity
            </Button>
          ) : (
            <Button icon={ShieldCheck} variant="secondary" to={`/lecturer/quizzes/${quiz.id}?step=monitoring`}>
              Open monitoring &amp; activity
            </Button>
          )}
        </div>
      </Card>
      <Card title="CSV reports" subtitle="Only students and results you are allowed to see. Files open in Excel or Google Sheets.">
        <CsvButtons quiz={quiz} />
      </Card>
      <ManualExport quiz={quiz} allApproved={allApproved} />
      <GoogleForms quiz={quiz} allApproved={allApproved} />
    </div>
  )
}
