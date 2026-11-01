import { CheckCircle2, Sparkles, XCircle } from 'lucide-react'
import { Alert, Button, ProgressBar } from '../ui'
import { duration } from '../../utils/format'

/** Live view of a generation run (stage, questions ready, rejected-by-check counts, timing). */
export default function GenerationProgress({ run, onCancel, cancelling }) {
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
        {run.grounded_on && <span>{run.grounded_on === 'reference_text' ? 'From your reference material' : 'From AI-written study notes'}</span>}
      </div>
      {rejected.length > 0 && (
        <div className="gen__rejected">
          <span>Rejected by the checks and regenerated:</span>
          {rejected.map(([k, n]) => <span key={k}>• {n} × {run.rejected_reasons?.[k] || k}</span>)}
        </div>
      )}
      {run.error && <Alert tone={run.status === 'partial' ? 'warning' : 'error'}>{run.error}</Alert>}
    </div>
  )
}
