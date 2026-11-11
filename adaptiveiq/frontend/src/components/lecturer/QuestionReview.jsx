import { useState } from 'react'
import { Check, Copy, History, Pencil, RotateCcw, ShieldCheck, Trash2, X } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { Alert, Button, ConfirmDialog, Dialog, Field, LoadingBlock, ErrorState, Textarea, useToast } from '../ui'
import { useApi } from '../../api/useApi'
import { dateTime } from '../../utils/format'
import QuestionCard from './QuestionCard'
import QuestionEditor from './QuestionEditor'
import { errText } from './util'

const HISTORY_TEXT = { approved: 'Approved', rejected: 'Rejected', edited: 'Edited', regenerated: 'Replaced by a regenerated question' }

function HistoryList({ id }) {
  const h = useApi(() => lecturerApi.questionHistory(id), [id])
  if (h.loading) return <LoadingBlock rows={2} label="Loading history" />
  if (h.error) return <ErrorState error={h.error} onRetry={h.reload} />
  if (!h.data.length) return <p className="muted">No review actions yet. The question was created and has not been reviewed.</p>
  return (
    <ol className="lc-timeline">
      {h.data.map((r, i) => {
        const changed = r.before && r.after ? diffFields(r.before, r.after) : []
        return (
          <li key={i}>
            <div className="row-between">
              <strong>{HISTORY_TEXT[r.action] || r.action}</strong>
              <span className="faint">{dateTime(r.at)}</span>
            </div>
            {r.note && <p className="muted">Note: {r.note}</p>}
            {changed.length > 0 && <p className="faint">Changed: {changed.join(', ')}</p>}
          </li>
        )
      })}
    </ol>
  )
}

function diffFields(a, b) {
  const out = []
  if (a.text !== b.text) out.push('question text')
  if (a.explanation !== b.explanation) out.push('explanation')
  if (a.difficulty !== b.difficulty) out.push('difficulty')
  const ao = (a.options || []).map((o) => o.text).join('|')
  const bo = (b.options || []).map((o) => o.text).join('|')
  if (ao !== bo) out.push('options')
  const ak = (a.options || []).find((o) => o.is_correct)?.label
  const bk = (b.options || []).find((o) => o.is_correct)?.label
  if (ak !== bk) out.push('correct answer')
  return out
}

/**
 * A question with its review controls: approve, reject with a note, edit (blocked once answered),
 * history, duplicate, delete. `extra` adds buttons (regenerate, remove from quiz, reorder).
 */
export default function QuestionReview({ q, index, objectives, onChanged, onDuplicated, onDeleted, extra, allowDelete = true, readOnly }) {
  const { notify } = useToast()
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState(null)

  const act = async (key, fn, okMsg) => {
    setBusy(key)
    setError(null)
    try {
      const r = await fn()
      if (okMsg) notify(okMsg)
      return r
    } catch (e) {
      setError(errText(e))
      notify(errText(e), 'error')
      return undefined
    } finally {
      setBusy(null)
    }
  }

  const failed = Boolean(q.validation?.failed_validation)
  const mathBlocked = ['wrong_key', 'no_match', 'ambiguous', 'unsupported', 'unchecked'].includes(q.validation?.math_status)
    || String(q.validation?.failure_reason || '').startsWith('math_')
  const approve = async () => {
    const r = await act('approve', () => lecturerApi.reviewQuestion(q.id, 'approve', null), 'Question approved')
    if (r) { onChanged?.(r); setDialog(null) }
  }
  const checkAgain = async () => {
    const r = await act('check', () => lecturerApi.checkQuality(q.id))
    if (r) {
      const st = r.validation?.quality?.status
      notify(r.validation?.failed_validation ? 'Checked: it still fails' : st === 'passed' ? 'Checked: AI review passed'
        : st === 'failed' ? 'Checked: AI review failed' : 'Checked with the Python checks (AI review not done)',
      r.validation?.failed_validation || st === 'failed' ? 'error' : undefined)
      onChanged?.(r)
    }
  }
  const reject = async () => {
    const r = await act('reject', () => lecturerApi.reviewQuestion(q.id, 'reject', note.trim() || null), 'Question rejected')
    if (r) { onChanged?.(r); setDialog(null); setNote('') }
  }
  const reset = async () => {
    const r = await act('reset', () => lecturerApi.reviewQuestion(q.id, 'reset', null), 'Moved back to review')
    if (r) onChanged?.(r)
  }
  const duplicate = async () => {
    const r = await act('dup', () => lecturerApi.duplicateQuestion(q.id), 'Copy created as a draft in the question bank')
    if (r) onDuplicated?.(r)
  }
  const remove = async () => {
    const r = await act('del', () => lecturerApi.deleteQuestion(q.id).then(() => true), 'Question deleted')
    if (r) { setDialog(null); onDeleted?.(q) }
  }
  const save = async (body) => {
    setBusy('edit')
    try {
      const r = await lecturerApi.editQuestion(q.id, body)
      notify(q.review_status === 'approved' ? 'Saved. Edited questions need approving again.' : 'Saved')
      onChanged?.(r)
      setDialog(null)
    } finally {
      setBusy(null)
    }
  }

  const actions = readOnly ? null : (
    <>
      {q.review_status !== 'approved' && (
        <Button size="sm" variant="teal" icon={Check} onClick={failed ? () => setDialog('approve-failed') : approve}
          disabled={mathBlocked}
          title={mathBlocked ? 'Numerical verification is failed or unchecked. Edit and run Check again first.' : undefined}
          loading={busy === 'approve'}>Approve</Button>
      )}
      {q.review_status !== 'rejected' && (
        <Button size="sm" variant="danger" icon={X} onClick={() => setDialog('reject')}>Reject</Button>
      )}
      {q.review_status !== 'draft' && q.review_status !== 'personal' && (
        <Button size="sm" variant="ghost" icon={RotateCcw} onClick={reset} loading={busy === 'reset'}>Back to review</Button>
      )}
      <Button size="sm" icon={Pencil} onClick={() => setDialog('edit')} disabled={q.locked}
        title={q.locked ? 'Students have answered this question' : undefined}>Edit</Button>
      {extra}
      {q.review_status !== 'personal' && q.review_status !== 'rejected' && (
        <Button size="sm" variant="ghost" icon={ShieldCheck} onClick={checkAgain} loading={busy === 'check'}
          title="Run the automatic checks and the AI review again on this version">Check again</Button>
      )}
      <Button size="sm" variant="ghost" icon={History} onClick={() => setDialog('history')}>History</Button>
      <Button size="sm" variant="ghost" icon={Copy} onClick={duplicate} loading={busy === 'dup'}>Duplicate</Button>
      {allowDelete && <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDialog('delete')} aria-label="Delete question">Delete</Button>}
    </>
  )

  return (
    <>
      <QuestionCard q={q} index={index} actions={actions}>
        {q.locked && !readOnly && (
          <p className="lc-note">Editing is locked because students have answered this question, so past results stay correct. Duplicate it and edit the copy.</p>
        )}
        {error && <Alert tone="error">{error}</Alert>}
      </QuestionCard>

      <Dialog open={dialog === 'edit'} onClose={() => setDialog(null)} title="Edit question" wide
        description={q.review_status === 'approved' ? 'Saving moves the question back to "Needs review" so it is approved again.' : undefined}>
        {dialog === 'edit' && (
          <QuestionEditor initial={q} objectives={objectives} onSubmit={save} onCancel={() => setDialog(null)} busy={busy === 'edit'} submitLabel="Save changes" />
        )}
      </Dialog>

      <Dialog open={dialog === 'reject'} onClose={() => setDialog(null)} title="Reject this question?"
        description="Rejected questions stay in the bank for the record but cannot be published."
        footer={<>
          <Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button>
          <Button variant="danger" onClick={reject} loading={busy === 'reject'}>Reject</Button>
        </>}>
        <Field label="Note (optional)" hint="Why it was rejected, for example a wrong key or an ambiguous option.">
          {(a) => <Textarea {...a} rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
      </Dialog>

      <Dialog open={dialog === 'history'} onClose={() => setDialog(null)} title="Review history">
        {dialog === 'history' && <HistoryList id={q.id} />}
      </Dialog>

      <ConfirmDialog open={dialog === 'approve-failed'} onClose={() => setDialog(null)} onConfirm={approve}
        title="Approve a question that failed the checks?" confirmLabel="Approve anyway" loading={busy === 'approve'}>
        <p className="muted">It failed: {q.validation?.failure_text || q.validation?.failure_reason}. Approve it only if you have read it and it is right. You can also edit it and press Check again.</p>
      </ConfirmDialog>

      <ConfirmDialog open={dialog === 'delete'} onClose={() => setDialog(null)} onConfirm={remove} tone="danger"
        title="Delete this question?" confirmLabel="Delete" loading={busy === 'del'}>
        <p className="muted">This cannot be undone. Questions used in a quiz or answered by students cannot be deleted; reject them instead.</p>
      </ConfirmDialog>
    </>
  )
}
