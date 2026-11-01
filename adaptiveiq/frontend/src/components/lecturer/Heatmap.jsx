import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Dialog, EmptyState, ErrorState, EvidenceMeter, Field, Input, LoadingBlock, MasteryChip, Select } from '../ui'
import { LABELS, dateTime, pct01, plural } from '../../utils/format'

const LEGEND = ['needs_improvement', 'developing', 'proficient', 'strong', 'insufficient_evidence', 'not_attempted']
const JUDGED = new Set(['needs_improvement', 'developing', 'proficient', 'strong'])

function cellText(c) {
  if (c.label === 'not_attempted') return '–'
  if (!JUDGED.has(c.label)) return '?'
  return Math.round(c.score * 100)
}

function cellLabel(student, topic, c) {
  const l = LABELS[c.label]?.text || c.label
  if (c.label === 'not_attempted') return `${student}, ${topic}: not attempted`
  if (!JUDGED.has(c.label)) return `${student}, ${topic}: insufficient evidence, ${plural(c.unique_questions ?? c.answers, 'question')} answered`
  return `${student}, ${topic}: ${l}, estimated ${Math.round(c.score * 100)} out of 100 from ${plural(c.unique_questions ?? c.answers, 'question')}`
}

export function HeatLegend() {
  return (
    <ul className="lc-legend" aria-label="Heatmap legend">
      {LEGEND.map((k) => (
        <li key={k}>
          <span className={`lc-swatch ${k === 'not_attempted' ? 'lc-swatch--none' : ''}`} style={k === 'not_attempted' ? undefined : { background: LABELS[k].color }} aria-hidden="true" />
          {LABELS[k].text}
          {k === 'insufficient_evidence' && <span className="faint">(?)</span>}
          {k === 'not_attempted' && <span className="faint">(–)</span>}
        </li>
      ))}
    </ul>
  )
}

/** Student x topic mastery heatmap. data: lecturerApi.heatmap response. */
export default function Heatmap({ data, courseId }) {
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('name')
  const [only, setOnly] = useState('all')
  const [open, setOpen] = useState(null)
  const gridRef = useRef(null)

  const rows = useMemo(() => {
    let list = data.students.map((s) => {
      const judged = s.cells.filter((c) => JUDGED.has(c.label))
      return { ...s, mean: judged.length ? judged.reduce((a, c) => a + c.score, 0) / judged.length : null,
        weak: s.cells.filter((c) => c.label === 'needs_improvement').length,
        attempted: s.cells.filter((c) => c.label !== 'not_attempted').length }
    })
    const needle = q.trim().toLowerCase()
    if (needle) list = list.filter((s) => `${s.name} ${s.roll_number || ''}`.toLowerCase().includes(needle))
    if (only === 'weak') list = list.filter((s) => s.weak > 0)
    if (only === 'none') list = list.filter((s) => s.attempted === 0)
    const byTopic = sort.startsWith('t:') ? Number(sort.slice(2)) : null
    list.sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'weak') return b.weak - a.weak || a.name.localeCompare(b.name)
      const va = byTopic != null ? scoreOf(a, byTopic) : a.mean
      const vb = byTopic != null ? scoreOf(b, byTopic) : b.mean
      if (va == null && vb == null) return a.name.localeCompare(b.name)
      if (va == null) return 1
      if (vb == null) return -1
      return va - vb
    })
    return list
  }, [data, q, sort, only])

  const onKey = (e) => {
    const el = e.target.closest('[data-r]')
    if (!el) return
    const r = Number(el.dataset.r)
    const c = Number(el.dataset.c)
    const d = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] }[e.key]
    if (!d) return
    const next = gridRef.current?.querySelector(`[data-r="${r + d[0]}"][data-c="${c + d[1]}"]`)
    if (next) { e.preventDefault(); next.focus() }
  }

  if (!data.topics.length) {
    return <EmptyState title="No topics in this course yet">Add units and topics to the course to see topic mastery here.</EmptyState>
  }
  if (!data.students.length) {
    return <EmptyState title="No students enrolled">Enrol students or share the join code. Their topic mastery appears once they answer questions.</EmptyState>
  }

  return (
    <div className="stack">
      <div className="lc-filters">
        <Field label="Search students">
          {(a) => (
            <div className="lc-search">
              <Search size={15} aria-hidden="true" />
              <Input {...a} type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or roll number" />
            </div>
          )}
        </Field>
        <Field label="Sort by">
          {(a) => (
            <Select {...a} value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="name">Name</option>
              <option value="mean">Lowest average mastery first</option>
              <option value="weak">Most weak topics first</option>
              {data.topics.map((t) => <option key={t.topic_id} value={`t:${t.topic_id}`}>Lowest in {t.topic}</option>)}
            </Select>
          )}
        </Field>
        <Field label="Show">
          {(a) => (
            <Select {...a} value={only} onChange={(e) => setOnly(e.target.value)}>
              <option value="all">All students</option>
              <option value="weak">With a weak topic</option>
              <option value="none">With no answers yet</option>
            </Select>
          )}
        </Field>
      </div>
      <HeatLegend />
      <p className="faint lc-small">Numbers are estimated mastery out of 100. “?” means fewer than 5 different questions answered, so there is not enough evidence to judge. “–” means the student has not answered any question on the topic. Use the arrow keys to move between cells; Enter opens the details.</p>
      {rows.length === 0 ? <p className="muted">No students match these filters.</p> : (
        <div className="lc-heat-wrap" ref={gridRef} onKeyDown={onKey}>
          <table className="lc-heat">
            <caption className="visually-hidden">Estimated topic mastery per student. Select a cell for the evidence behind it.</caption>
            <thead>
              <tr>
                <th scope="col" className="lc-heat__corner">Student</th>
                {data.topics.map((t) => (
                  <th key={t.topic_id} scope="col" title={`${t.subject} › ${t.unit}`}><span>{t.topic}</span></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((s, r) => (
                <tr key={s.student_id}>
                  <th scope="row">
                    <Link className="lc-heat__name" to={`/lecturer/students/${s.student_id}`}>{s.name}</Link>
                    {s.roll_number && <span className="faint">{s.roll_number}</span>}
                  </th>
                  {data.topics.map((t, c) => {
                    const cell = s.cells.find((x) => x.topic_id === t.topic_id) || { label: 'not_attempted', answers: 0 }
                    return (
                      <td key={t.topic_id}>
                        <button type="button" className="lc-heat__cell" data-label={cell.label} data-r={r} data-c={c}
                          style={{ '--cell': LABELS[cell.label]?.color }}
                          aria-label={cellLabel(s.name, t.topic, cell)}
                          onClick={() => setOpen({ student: s, topic: t })}>
                          {cellText(cell)}
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <CellDialog courseId={courseId} open={open} onClose={() => setOpen(null)} />
    </div>
  )
}

function scoreOf(s, topicId) {
  const c = s.cells.find((x) => x.topic_id === topicId)
  return c && JUDGED.has(c.label) ? c.score : null
}

function CellDialog({ courseId, open, onClose }) {
  return (
    <Dialog open={!!open} onClose={onClose} wide
      title={open ? `${open.student.name} · ${open.topic.topic}` : ''}
      description="The evidence behind this estimate. It is an estimate from answers so far, not a final judgement.">
      {open && <CellDetail courseId={courseId} studentId={open.student.student_id} topicId={open.topic.topic_id} />}
    </Dialog>
  )
}

const EVIDENCE_TEXT = { none: 'No evidence', low: 'Insufficient evidence', moderate: 'Limited evidence', high: 'Stronger evidence' }

export function CellDetail({ courseId, studentId, topicId }) {
  const d = useApi(() => lecturerApi.heatmapCell(courseId, studentId, topicId), [courseId, studentId, topicId])
  if (d.loading) return <LoadingBlock rows={3} label="Loading cell details" />
  if (d.error) return <ErrorState error={d.error} onRetry={d.reload} />
  const { estimate: e, attempts, common_mistakes: mistakes } = d.data
  const answered = e ? e.correct + e.incorrect : 0
  return (
    <div className="stack">
      {!e ? (
        <Alert tone="info" title="Not attempted">{d.data.status_reason || 'The student has not answered any question on this topic yet.'}</Alert>
      ) : (
        <>
          <div className="lc-cell-head">
            <div>
              <p className="lc-mini-label">Estimated mastery</p>
              {e.label === 'insufficient_evidence'
                ? <p className="lc-big">Not enough evidence</p>
                : <p className="lc-big num">{Math.round(e.score * 100)}<span className="faint">/100</span></p>}
              <p className="faint lc-small">Likely range {Math.round(e.lower * 100)}–{Math.round(e.upper * 100)}</p>
            </div>
            <div className="stack" style={{ gap: 'var(--space-2)' }}>
              <MasteryChip label={e.label} />
              <span className="row" style={{ gap: 8 }}><EvidenceMeter level={e.evidence_level} /><span className="lc-small muted">{EVIDENCE_TEXT[e.evidence_level]}</span></span>
            </div>
          </div>
          <dl className="lc-dl lc-dl--grid">
            <div><dt>Questions attempted</dt><dd>{plural(e.unique_questions, 'different question')} ({plural(e.answers, 'answer')})</dd></div>
            <div><dt>Correct / incorrect</dt><dd>{e.correct} correct, {e.incorrect} incorrect</dd></div>
            <div><dt>Skipped (counted separately)</dt><dd>{e.skipped}</dd></div>
            <div><dt>Accuracy of answered</dt><dd>{answered ? pct01(e.correct / answered) : '—'}</dd></div>
            <div><dt>Recent performance</dt><dd>{e.recent_accuracy != null ? `${pct01(e.recent_accuracy)} of the last ${e.recent_n}` : '—'}</dd></div>
            <div><dt>Trend</dt><dd>{e.trend === 'not_enough_data' ? 'Not enough data for a trend' : e.trend}</dd></div>
          </dl>
          <p className="muted lc-small">{e.explanation}</p>
        </>
      )}
      <div className="lc-callout">
        <p className="lc-mini-label">Suggested intervention</p>
        <p>{d.data.suggested_intervention}</p>
        {d.data.status_reason && e && <p className="faint lc-small">{d.data.status_reason}</p>}
      </div>
      <div>
        <h3 className="lc-h3">Relevant attempts</h3>
        {attempts.length === 0 ? <p className="muted">No submitted attempts include this topic.</p> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Quiz</th><th>Submitted</th><th className="num">Correct</th><th className="num">Incorrect</th><th className="num">Skipped</th></tr></thead>
              <tbody>
                {attempts.map((a) => (
                  <tr key={a.session_id}>
                    <td>{a.quiz}{a.kind === 'practice' && <span className="faint"> (AI practice, not reviewed)</span>}</td>
                    <td>{dateTime(a.at)}</td>
                    <td className="num">{a.correct}</td><td className="num">{a.incorrect}</td><td className="num">{a.skipped}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div>
        <h3 className="lc-h3">Common mistakes</h3>
        {mistakes.length === 0 ? <p className="muted">No repeated wrong choices in your quizzes.</p> : (
          <ul className="list-plain">
            {mistakes.map((m) => (
              <li key={`${m.question_id}-${m.chosen}`} className="lc-mistake">
                <p>{m.question}</p>
                <p className="faint lc-small">Chose “{m.chosen}”{m.times > 1 ? ` ${m.times} times` : ''}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
