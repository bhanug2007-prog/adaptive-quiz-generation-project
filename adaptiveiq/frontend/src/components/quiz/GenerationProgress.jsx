import { CheckCircle2, Sparkles, XCircle } from 'lucide-react'
import { Alert, Button, ProgressBar } from '../ui'
import { duration } from '../../utils/format'
import AgentLog, { generationLog } from '../lecturer/AgentSteps'

/** Live view of a generation run (stage, questions ready, rejected-by-check counts, timing). */
export default function GenerationProgress({ run, onCancel, cancelling, showQuality = true }) {
  if (!run) return null
  const active = run.status === 'queued' || run.status === 'running'
  const rejected = Object.entries(run.rejected || {}).filter(([, n]) => n > 0)
  const remaining = run.avg_question_s > 0 && active ? Math.max(0, (run.total - run.ready) * run.avg_question_s) : null
  return (
    <div className="gen" aria-live="polite">
      <div className="row-between">
        <div className="gen__stage">
          {active ? <span className="spinner" aria-hidden="true" /> : run.status === 'failed' || run.status === 'cancelled'
            ? <XCircle size={18} color="var(--error)" aria-hidden="true" /> : <CheckCircle2 size={18} color="var(--success)" aria-hidden="true" />}
          <span>{run.status === 'queued' && run.queue_position ? `Waiting in queue (position ${run.queue_position})` : run.stage}</span>
        </div>
        {active && onCancel && <Button size="sm" variant="ghost" onClick={onCancel} loading={cancelling}>Cancel</Button>}
      </div>
      <ProgressBar value={run.ready} max={run.total} label="Questions ready" tone="accent" />
      <div className="gen__meta">
        <span><Sparkles size={12} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-1px', color: 'var(--accent)' }} /> {run.ready} of {run.total} questions passed the checks</span>
        <span>{run.attempts} model calls</span>
        <span>Elapsed {duration(run.elapsed_s)}</span>
        {run.avg_question_s > 0 && <span>{run.avg_question_s < 1 ? 'Under 1 s per question' : `About ${duration(run.avg_question_s)} per question`}</span>}
        {remaining != null && <span>About {duration(remaining)} left (estimate)</span>}
        {run.grounded_on && (
          <span>
            {run.grounded_on === 'document'
              ? `From uploaded document${run.document_name ? ` (${run.document_name})` : ''}`
              : run.grounded_on === 'reference_text'
                ? 'From your reference material'
                : 'From AI-written study notes'}
          </span>
        )}
      </div>
      {run.insufficient_content_note && (
        <Alert tone="warning" title="Adjusted for available document material">
          {run.insufficient_content_note}
        </Alert>
      )}
      {rejected.length > 0 && (
        <div className="gen__rejected">
          <span>Rejected by the checks and regenerated:</span>
          {rejected.map(([k, n]) => <span key={k}>• {n} × {run.rejected_reasons?.[k] || k}</span>)}
        </div>
      )}
      {showQuality && !active && <QualitySummary q={run.quality} />}
      {run.error && <Alert tone={run.status === 'partial' ? 'warning' : 'error'}>{run.error}</Alert>}
      {showQuality && !active && run.run_id && <AgentLog load={generationLog(run.run_id)} title="What the generation agent did"
        summary="Each tool the Question Quality Agent ran and each decision it took, with the reason. It saves drafts only; publishing is always your action." />}
    </div>
  )
}

const LEVEL_ORDER = ['easy', 'medium', 'hard']
const mix = (m) => LEVEL_ORDER.filter((l) => m?.[l]).map((l) => `${m[l]} ${l}`).join(', ') || 'none'

/** After a run: whether the AI reviewer was used, and the requested vs judged difficulty mix. */
function QualitySummary({ q }) {
  if (!q) return null
  const ai = { used: 'AI review: used on every question', partly: 'AI review: used on some questions', not_used: 'AI review: not done' }[q.ai_review]
  return (
    <div className="gen__quality">
      <p>{ai}{q.ai_model ? ` (${q.ai_model})` : ''}{q.ai_note ? `. ${q.ai_note}` : ''}</p>
      {q.question_count > 0 && (
        <p>
          Difficulty mix requested: {mix(q.requested)}.{' '}
          {q.assessed_count > 0
            ? `Judged by the AI reviewer: ${mix(q.ai_assessed)}${q.mix_matches === true ? ', which matches.' : q.mix_matches === false ? `, which does not match (${q.mismatched_question_ids.length} ${q.mismatched_question_ids.length === 1 ? 'question differs' : 'questions differ'}).` : '.'}`
            : 'Not checked by the AI reviewer, so the labels are the requested ones.'}
        </p>
      )}
      {q.failed_kept > 0 && <p><strong>{q.failed_kept} {q.failed_kept === 1 ? 'question' : 'questions'} kept with &quot;Failed checks&quot;.</strong> They are not approved. Fix, regenerate or reject them before publishing.</p>}
    </div>
  )
}
