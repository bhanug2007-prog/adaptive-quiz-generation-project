import { BarChart3 } from 'lucide-react'
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { date, dateTime, pct, pct01 } from '../../utils/format'

/* Recharts reads colours as SVG attributes; CSS variables work there in every current browser. */
const C = {
  teal: 'var(--teal)', accent: 'var(--accent)', grid: 'var(--border)', axis: 'var(--text-3)', text: 'var(--text-2)',
  surface: 'var(--card)',
}
/** Tick labels: dates when the data spans days, times when it all happened within about a day. */
function timeTicks(rows) {
  const ts = rows.map((r) => r.t)
  const span = ts.length ? Math.max(...ts) - Math.min(...ts) : 0
  const f = new Intl.DateTimeFormat(undefined, span < 2 * 86400000 ? { hour: '2-digit', minute: '2-digit' } : { day: 'numeric', month: 'short' })
  return (v) => f.format(new Date(v))
}
const AXIS = { stroke: C.grid, tick: { fill: C.axis, fontSize: 12 }, tickLine: false }

/** Readable dark tooltip. rows: [{name, value, color}] */
export function TipBox({ title, rows }) {
  return (
    <div className="st-tip">
      {title && <p className="st-tip__title">{title}</p>}
      {rows.map((r) => (
        <p key={r.name} className="st-tip__row">
          {r.color && <span className="st-tip__swatch" style={{ background: r.color }} aria-hidden="true" />}
          <span>{r.name}</span>
          <strong className="num">{r.value}</strong>
        </p>
      ))}
    </div>
  )
}

/** Title, caption, the chart (aria-hidden), and a table for screen readers and anyone who prefers numbers. */
export function ChartFrame({ title, caption, note, empty, emptyText, table, height = 240, children }) {
  return (
    <figure className="st-chart">
      <figcaption className="st-chart__head">
        <span className="st-chart__title">{title}</span>
        {caption && <span className="st-chart__cap">{caption}</span>}
      </figcaption>
      {empty ? (
        <div className="st-chart__empty" style={{ minHeight: Math.min(height, 180) }}>
          <BarChart3 size={18} aria-hidden="true" />
          <p>{emptyText}</p>
        </div>
      ) : (
        <>
          {note && <p className="st-chart__note">{note}</p>}
          <div className="st-chart__plot" style={{ height }} aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
          </div>
          {table && (
            <details className="st-chart__table">
              <summary>View as table</summary>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr>{table.head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
                  <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={j ? 'num' : undefined}>{c}</td>)}</tr>)}</tbody>
                </table>
              </div>
            </details>
          )}
        </>
      )}
    </figure>
  )
}

/** Mastery estimate over time for one topic, with the likely range as a band. points from mastery/history. */
export function MasteryHistoryChart({ history, topicName }) {
  const pts = (history?.points || []).filter((p) => p.score != null).map((p) => ({
    t: new Date(p.at).getTime(), score: Math.round(p.score * 100),
    band: [Math.round((p.lower ?? p.score) * 100), Math.round((p.upper ?? p.score) * 100)], answers: p.answers, label: p.label,
  }))
  const enough = history?.enough_data
  return (
    <ChartFrame
      title={`Mastery over time${topicName ? `: ${topicName}` : ''}`}
      caption="Estimate out of 100 after each submitted quiz; the shaded band is the likely range."
      empty={pts.length < 2}
      emptyText={pts.length === 1
        ? 'Only one estimate so far. Finish another quiz on this topic to see how it changes.'
        : 'No estimates for this topic yet. Submit a quiz on it to start the history.'}
      note={!enough ? 'Not enough estimates yet to call this a trend (needs at least 3).' : null}
      table={{ head: ['When', 'Estimate', 'Likely range', 'Answers'], rows: pts.map((p) => [dateTime(p.t), `${p.score}/100`, `${p.band[0]}–${p.band[1]}`, p.answers]) }}>
      <ComposedChart data={pts} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={timeTicks(pts)} {...AXIS} minTickGap={32} padding={{ left: 16, right: 16 }} />
        <YAxis domain={[0, 100]} ticks={[0, 50, 70, 100]} {...AXIS} axisLine={false} width={40}
          label={{ value: 'Mastery', angle: -90, position: 'insideLeft', offset: 14, fill: C.axis, fontSize: 12 }} />
        <Tooltip cursor={{ stroke: C.axis, strokeWidth: 1 }}
          content={({ active, payload }) => active && payload?.length ? (
            <TipBox title={dateTime(payload[0].payload.t)} rows={[
              { name: 'Estimate', value: `${payload[0].payload.score}/100`, color: C.teal },
              { name: 'Likely range', value: `${payload[0].payload.band[0]}–${payload[0].payload.band[1]}` },
              { name: 'Answers', value: payload[0].payload.answers },
            ]} />) : null} />
        <Area dataKey="band" stroke="none" fill={C.teal} fillOpacity={0.14} isAnimationActive={false} />
        <Line dataKey="score" stroke={C.teal} strokeWidth={2} dot={{ r: 4, fill: C.teal, stroke: C.surface, strokeWidth: 2 }}
          activeDot={{ r: 6, stroke: C.surface, strokeWidth: 2 }} animationDuration={500} />
      </ComposedChart>
    </ChartFrame>
  )
}

/** Final percentage of every submitted quiz with released results: assessments (teal) and practice (purple). */
export function ScoresChart({ scores, enough }) {
  const rows = (scores || []).map((s) => ({
    t: new Date(s.at).getTime(), title: s.title, kind: s.kind,
    assessment: s.kind === 'assessment' ? s.percentage : null, practice: s.kind === 'practice' ? s.percentage : null,
  }))
  return (
    <ChartFrame title="Score over time" caption="Final percentage of each submitted quiz."
      empty={!rows.length} emptyText="No results yet. Submit a quiz and your scores will appear here."
      note={!enough && rows.length ? 'Fewer than 3 results, so this is not a trend yet.' : null}
      table={{ head: ['When', 'Quiz', 'Type', 'Score'], rows: rows.map((r) => [dateTime(r.t), r.title, r.kind === 'practice' ? 'Practice' : 'Assessment', pct(r.assessment ?? r.practice)]) }}>
      <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={timeTicks(rows)} {...AXIS} minTickGap={32}
          padding={{ left: 16, right: 16 }} />
        <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} {...AXIS} axisLine={false} width={46} />
        <Tooltip cursor={{ stroke: C.axis, strokeWidth: 1 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const r = payload[0].payload
            return <TipBox title={r.title} rows={[
              { name: r.kind === 'practice' ? 'Practice' : 'Assessment', value: pct(r.assessment ?? r.practice), color: r.kind === 'practice' ? C.accent : C.teal },
              { name: 'Submitted', value: dateTime(r.t) },
            ]} />
          }} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: 'var(--text-2)' }} />
        <Line name="Assessments" dataKey="assessment" stroke={C.teal} strokeWidth={2} connectNulls
          dot={{ r: 4, fill: C.teal, stroke: C.surface, strokeWidth: 2 }} activeDot={{ r: 6 }} animationDuration={500} />
        <Line name="Practice (AI-generated)" dataKey="practice" stroke={C.accent} strokeWidth={2} connectNulls
          dot={{ r: 4, fill: C.accent, stroke: C.surface, strokeWidth: 2 }} activeDot={{ r: 6 }} animationDuration={500} />
      </LineChart>
    </ChartFrame>
  )
}

/** Questions answered per week, practice and assessment stacked. */
export function WeeklyActivityChart({ weeks }) {
  const rows = (weeks || []).map((w) => ({ ...w, label: date(w.week) }))
  return (
    <ChartFrame title="Practice activity by week" caption="Questions answered in submitted quizzes, by week starting Monday."
      empty={!rows.length} emptyText="No activity yet. Answered questions are counted here each week."
      table={{ head: ['Week of', 'Practice', 'Assessment'], rows: rows.map((r) => [r.label, r.practice, r.assessment]) }}>
      <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }} barCategoryGap="30%">
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="label" {...AXIS} />
        <YAxis allowDecimals={false} {...AXIS} axisLine={false} width={40}
          label={{ value: 'Questions', angle: -90, position: 'insideLeft', offset: 14, fill: C.axis, fontSize: 12 }} />
        <Tooltip cursor={{ fill: 'var(--hover)' }}
          content={({ active, payload, label }) => active && payload?.length ? (
            <TipBox title={`Week of ${label}`} rows={payload.map((p) => ({ name: p.name, value: p.value, color: p.color }))} />) : null} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: 'var(--text-2)' }} />
        <Bar name="Practice" dataKey="practice" stackId="a" fill={C.accent} maxBarSize={36} stroke={C.surface} strokeWidth={2} />
        <Bar name="Assessment" dataKey="assessment" stackId="a" fill={C.teal} radius={[4, 4, 0, 0]} maxBarSize={36} stroke={C.surface} strokeWidth={2} />
      </BarChart>
    </ChartFrame>
  )
}

/** Accuracy at each confidence level. Only drawn once the API says there are enough rated answers. */
export function CalibrationChart({ data }) {
  const rows = (data?.levels || []).map((l) => ({ ...l, acc: l.accuracy == null ? null : Math.round(l.accuracy * 100) }))
  return (
    <ChartFrame title="Accuracy by confidence" caption="How often you were right when you said Guessing, Unsure or Sure." height={200}
      empty={!data || data.rated < data.min_needed} emptyText={data?.message || 'Not enough rated answers yet.'}
      table={{ head: ['Confidence', 'Answers', 'Accuracy'], rows: rows.map((r) => [r.name, r.answers, r.acc == null ? 'Too few answers' : pct01(r.accuracy)]) }}>
      <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }} barCategoryGap="35%">
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="name" {...AXIS} />
        <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tickFormatter={(v) => `${v}%`} {...AXIS} axisLine={false} width={46} />
        <Tooltip cursor={{ fill: 'var(--hover)' }}
          content={({ active, payload }) => active && payload?.length ? (
            <TipBox title={payload[0].payload.name} rows={[
              { name: 'Accuracy', value: payload[0].payload.acc == null ? 'Too few answers' : `${payload[0].payload.acc}%`, color: C.teal },
              { name: 'Answers', value: payload[0].payload.answers },
            ]} />) : null} />
        <Bar dataKey="acc" name="Accuracy" fill={C.teal} radius={[4, 4, 0, 0]} maxBarSize={56} />
      </BarChart>
    </ChartFrame>
  )
}
