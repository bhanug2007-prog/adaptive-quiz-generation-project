import { useReducedMotion } from 'framer-motion'
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { LABELS } from '../../utils/format'

const AXIS = { stroke: 'var(--text-3)', fontSize: 12, tickLine: false }
const GRID = { stroke: 'var(--border)', strokeDasharray: '0', vertical: false }
export const TOOLTIP = {
  contentStyle: {
    background: 'var(--elevated)', border: '1px solid var(--border-strong)', borderRadius: 8,
    color: 'var(--text)', fontSize: 13, boxShadow: 'var(--shadow-lift)',
  },
  labelStyle: { color: 'var(--text)', fontWeight: 600, marginBottom: 4 },
  itemStyle: { color: 'var(--text-2)' },
  cursor: { fill: 'var(--hover)', fillOpacity: 0.6 },
}

/** A chart with a heading, a one-line reading, and the same numbers as a table for screen readers. */
export function ChartFigure({ title, summary, table, children, height = 240, empty }) {
  return (
    <figure className="lc-chart">
      <figcaption>
        <h3 className="lc-chart__title">{title}</h3>
        {summary && <p className="lc-chart__sum">{summary}</p>}
      </figcaption>
      {empty ? <div className="lc-chart__empty">{empty}</div> : (
        <>
          <div className="lc-chart__plot" style={{ height }} aria-hidden="true">{children}</div>
          {table && (
            <details className="lc-details lc-chart__table">
              <summary>Show as table</summary>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr>{table.head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
                  <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
                </table>
              </div>
            </details>
          )}
        </>
      )}
    </figure>
  )
}

/** Single-series vertical bars. data: [{name, value, ...}] */
export function SimpleBars({ data, color = 'var(--teal)', yLabel, xLabel, yMax, valueFormat = (v) => v, tooltipName = 'Value', colorFor, xTickFormat }) {
  const reduce = useReducedMotion()
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: xLabel ? 22 : 4, left: yLabel ? 18 : 4 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="name" {...AXIS} interval={0} tick={{ fill: 'var(--text-2)', fontSize: 11 }} tickFormatter={xTickFormat}
          label={xLabel ? { value: xLabel, position: 'insideBottom', offset: -12, fill: 'var(--text-3)', fontSize: 12 } : undefined} />
        <YAxis {...AXIS} tick={{ fill: 'var(--text-2)', fontSize: 11 }} allowDecimals={false} domain={[0, yMax || 'auto']} width={44}
          tickFormatter={valueFormat}
          label={yLabel ? { value: yLabel, angle: -90, position: 'left', offset: 2, fill: 'var(--text-3)', fontSize: 12, style: { textAnchor: 'middle' } } : undefined} />
        <Tooltip {...TOOLTIP} formatter={(v) => [v == null ? 'No data' : valueFormat(v), tooltipName]} />
        <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} maxBarSize={44} isAnimationActive={!reduce}>
          {colorFor && data.map((d, i) => <Cell key={i} fill={colorFor(d)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function TrendLine({ data, yLabel = 'Class average (%)' }) {
  const reduce = useReducedMotion()
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 18 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="name" {...AXIS} tick={{ fill: 'var(--text-2)', fontSize: 11 }} />
        <YAxis {...AXIS} domain={[0, 100]} tick={{ fill: 'var(--text-2)', fontSize: 11 }} width={44}
          label={{ value: yLabel, angle: -90, position: 'left', offset: 2, fill: 'var(--text-3)', fontSize: 12, style: { textAnchor: 'middle' } }} />
        <Tooltip {...TOOLTIP} cursor={{ stroke: 'var(--border-strong)' }} formatter={(v) => [v == null ? 'No submissions' : `${v}%`, 'Average']} />
        <Line type="monotone" dataKey="value" stroke="var(--teal)" strokeWidth={2} dot={{ r: 4, fill: 'var(--teal)', stroke: 'var(--card)', strokeWidth: 2 }}
          activeDot={{ r: 6 }} connectNulls isAnimationActive={!reduce} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export const MASTERY_ORDER = ['needs_improvement', 'developing', 'proficient', 'strong', 'insufficient_evidence', 'not_attempted']

/** One 100% stacked bar per topic, built with plain HTML so each segment can be labelled. */
export function MasteryStacks({ rows }) {
  return (
    <div className="lc-stacks">
      <ul className="lc-legend" aria-label="Legend">
        {MASTERY_ORDER.map((k) => (
          <li key={k}><span className="lc-swatch" style={{ background: LABELS[k].color }} aria-hidden="true" />{LABELS[k].text}</li>
        ))}
      </ul>
      {rows.map((r) => {
        const total = MASTERY_ORDER.reduce((s, k) => s + (r.counts[k] || 0), 0)
        const desc = MASTERY_ORDER.filter((k) => r.counts[k]).map((k) => `${LABELS[k].text}: ${r.counts[k]}`).join(', ')
        return (
          <div key={r.topic_id} className="lc-stack-row">
            <div className="lc-stack-row__label">
              <span>{r.topic}</span>
              <span className="faint">{r.unit}</span>
            </div>
            <div className="lc-stack" role="img" aria-label={`${r.topic}: ${desc || 'no students'}`}>
              {total === 0 ? <span className="lc-stack__none">No students</span> : MASTERY_ORDER.filter((k) => r.counts[k]).map((k) => (
                <span key={k} className="lc-stack__seg" title={`${LABELS[k].text}: ${r.counts[k]} of ${total}`}
                  style={{ flexGrow: r.counts[k], background: LABELS[k].color }}>
                  <span className="lc-stack__n">{r.counts[k]}</span>
                </span>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
