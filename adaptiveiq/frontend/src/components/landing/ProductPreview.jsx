import { useRef, useState } from 'react'
import { Clock, Flame, GraduationCap, Presentation, Sparkles, TriangleAlert } from 'lucide-react'
import Reveal, { SectionHead } from './Reveal'
import Ring from './Ring'

/* Everything in this file is illustrative example data for the preview only.
   It is never mixed with real accounts and is labelled "Example data" on screen. */
const STUDENT_TOPICS = [
  { name: 'Probability basics', score: 81, label: 'Proficient', color: 'var(--m-proficient)' },
  { name: 'Conditional probability', score: 72, label: 'Proficient', color: 'var(--m-proficient)' },
  { name: 'Random variables', score: 56, label: 'Developing', color: 'var(--m-developing)' },
  { name: 'Bayes’ theorem', score: 38, label: 'Needs improvement', color: 'var(--m-needs)' },
  { name: 'Distributions', score: null, label: 'Insufficient evidence', color: 'var(--m-insufficient)', note: '3 questions so far' },
]
const STUDENT_QUIZZES = [
  { title: 'Unit 2 assessment', kind: 'Assigned · lecturer-reviewed', score: '8 / 10', extra: null },
  { title: 'Practice: Bayes’ theorem', kind: 'Practice · AI-generated', score: '5 / 10', extra: '1 skipped' },
  { title: 'Practice: Random variables', kind: 'Practice · AI-generated', score: '7 / 10', extra: null },
]
const STREAK = [1, 1, 0, 1, 1, 1, 1]

const HEAT_TOPICS = ['Basics', 'Conditional', 'Random var.', 'Bayes', 'Distrib.']
const HEAT = [
  ['S-01', ['proficient', 'proficient', 'developing', 'needs', 'insufficient']],
  ['S-02', ['strong', 'proficient', 'proficient', 'developing', 'developing']],
  ['S-03', ['developing', 'needs', 'needs', 'needs', 'insufficient']],
  ['S-04', ['proficient', 'developing', 'developing', 'needs', 'insufficient']],
  ['S-05', ['strong', 'strong', 'proficient', 'developing', 'proficient']],
  ['S-06', ['proficient', 'developing', 'needs', 'needs', 'insufficient']],
]
const HEAT_TEXT = {
  strong: 'Strong', proficient: 'Proficient', developing: 'Developing', needs: 'Needs improvement', insufficient: 'Insufficient evidence',
}

function Panel({ title, children, className = '', aside }) {
  return (
    <div className={`lp-pv-panel ${className}`}>
      <div className="lp-pv-panel__head">
        <p className="lp-pv-panel__title">{title}</p>
        {aside}
      </div>
      {children}
    </div>
  )
}

function StudentPreview() {
  return (
    <div className="lp-pv-grid lp-pv-grid--student">
      <Panel title="Overall progress" className="lp-pv-a">
        <div className="lp-pv-overall">
          <Ring value={64} size={92} stroke={8} caption="of 100" label="Overall estimate 64 out of 100" />
          <div className="lp-pv-overall__text">
            <p><span className="num lp-strong">4</span> of 5 topics with enough evidence</p>
            <p className="lp-dim">42 questions answered · 31 correct · 3 skipped</p>
          </div>
        </div>
      </Panel>
      <Panel title="Learning streak" className="lp-pv-b" aside={<Flame size={14} className="lp-warn" aria-hidden="true" />}>
        <p className="lp-pv-big num">6 <span>days</span></p>
        <div className="lp-streak" aria-label="Practised on 6 of the last 7 days">
          {STREAK.map((d, i) => <span key={i} className={d ? 'is-on' : ''} />)}
        </div>
      </Panel>
      <Panel title="Topic mastery" className="lp-pv-c">
        <ul className="lp-pv-topics">
          {STUDENT_TOPICS.map((t) => (
            <li key={t.name}>
              <div className="lp-pv-topic__row">
                <span className="lp-pv-topic__name">{t.name}</span>
                <span className="lp-pv-topic__score num">{t.score == null ? '—' : `${t.score}/100`}</span>
              </div>
              <div className="lp-bar"><span style={{ '--w': `${t.score ?? 0}%`, '--c': t.color }} /></div>
              <span className="lp-pv-topic__label"><i style={{ background: t.color }} />{t.label}{t.note ? ` · ${t.note}` : ''}</span>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Recent quizzes" className="lp-pv-d">
        <ul className="lp-pv-list">
          {STUDENT_QUIZZES.map((q) => (
            <li key={q.title}>
              <div>
                <p className="lp-pv-list__title">{q.title}</p>
                <p className="lp-dim">{q.kind}</p>
              </div>
              <div className="lp-pv-list__end">
                <span className="num">{q.score}</span>
                {q.extra && <span className="lp-dim">{q.extra}</span>}
              </div>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Recommended practice" className="lp-pv-e">
        <div className="lp-pv-rec">
          <p className="lp-pv-rec__title"><Sparkles size={14} aria-hidden="true" />Bayes’ theorem · Easy</p>
          <p className="lp-dim">4 of your last 6 answers here were incorrect. Step back one level and rebuild.</p>
        </div>
        <div className="lp-pv-rec lp-pv-rec--teal">
          <p className="lp-pv-rec__title"><Clock size={14} aria-hidden="true" />Revise conditional probability</p>
          <p className="lp-dim">Due today on your 3-day revision interval.</p>
        </div>
      </Panel>
    </div>
  )
}

function LecturerPreview() {
  return (
    <div className="lp-pv-grid lp-pv-grid--lecturer">
      <Panel title="Class participation" className="lp-pv-a">
        <p className="lp-pv-big num">34 <span>of 41 students</span></p>
        <div className="lp-bar lp-bar--lg"><span style={{ '--w': '83%', '--c': 'var(--teal)' }} /></div>
        <p className="lp-dim">attempted the Unit 2 assessment</p>
      </Panel>
      <Panel title="Average assessment score" className="lp-pv-b">
        <p className="lp-pv-big num">68<span>%</span></p>
        <p className="lp-dim">Unit 2 assessment · 34 submissions</p>
      </Panel>
      <Panel title="Topic mastery heatmap" className="lp-pv-c lp-pv-heat-panel">
        <div className="lp-heat" role="table" aria-label="Example student by topic mastery">
          <div role="row" className="lp-heat__row lp-heat__row--head">
            <span role="columnheader" className="lp-heat__name"><span className="visually-hidden">Student</span></span>
            {HEAT_TOPICS.map((t) => <span role="columnheader" key={t}>{t}</span>)}
          </div>
          {HEAT.map(([name, cells]) => (
            <div role="row" className="lp-heat__row" key={name}>
              <span role="rowheader" className="lp-heat__name">{name}</span>
              {cells.map((c, i) => (
                <span role="cell" key={i} className={`lp-heat__cell lp-heat--${c}`} title={`${name} · ${HEAT_TOPICS[i]}: ${HEAT_TEXT[c]}`}>
                  <span className="visually-hidden">{HEAT_TEXT[c]}</span>
                </span>
              ))}
            </div>
          ))}
        </div>
        <ul className="lp-heat__legend" aria-label="Legend">
          {Object.entries(HEAT_TEXT).map(([k, v]) => <li key={k}><i className={`lp-heat--${k}`} />{v}</li>)}
        </ul>
      </Panel>
      <Panel title="At-risk learning gaps" className="lp-pv-d" aside={<TriangleAlert size={14} className="lp-warn" aria-hidden="true" />}>
        <ul className="lp-pv-list">
          <li>
            <div>
              <p className="lp-pv-list__title">Bayes’ theorem</p>
              <p className="lp-dim">14 students below 50 · plan a revision session</p>
            </div>
          </li>
          <li>
            <div>
              <p className="lp-pv-list__title">Q7 · Random variables</p>
              <p className="lp-dim">Missed by 71% of 34 · check the wording</p>
            </div>
          </li>
          <li>
            <div>
              <p className="lp-pv-list__title">Distributions</p>
              <p className="lp-dim">Too few answers to judge · assign practice</p>
            </div>
          </li>
        </ul>
      </Panel>
      <Panel title="Recent quizzes" className="lp-pv-e">
        <ul className="lp-pv-list">
          <li><div><p className="lp-pv-list__title">Unit 2 assessment</p><p className="lp-dim">Published · 20% of grade</p></div><span className="num lp-pv-list__end">34 / 41</span></li>
          <li><div><p className="lp-pv-list__title">Unit 3 quiz (draft)</p><p className="lp-dim">8 of 12 questions approved</p></div><span className="num lp-pv-list__end">—</span></li>
        </ul>
      </Panel>
    </div>
  )
}

const VIEWS = [
  { id: 'student', label: 'Student', icon: GraduationCap, title: 'Student overview' },
  { id: 'lecturer', label: 'Lecturer', icon: Presentation, title: 'Class overview' },
]

export default function ProductPreview() {
  const [view, setView] = useState('student')
  const refs = useRef([])
  const onKey = (e, i) => {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!d) return
    e.preventDefault()
    const n = (i + d + VIEWS.length) % VIEWS.length
    setView(VIEWS[n].id)
    refs.current[n]?.focus()
  }
  const current = VIEWS.find((v) => v.id === view)
  return (
    <section id="preview" className="lp-section lp-section--preview" aria-labelledby="lp-preview-title">
      <div className="container">
        <SectionHead id="lp-preview-title" eyebrow="Product preview" align="center"
          title="One platform, two views of the same learning."
          lead="Students see what to practise next. Lecturers see where the class stands, topic by topic." />
        <Reveal className="lp-pv">
          <div className="lp-pv__bar">
            <div className="lp-pv__toggle" role="tablist" aria-label="Preview">
              {VIEWS.map((v, i) => (
                <button key={v.id} ref={(el) => (refs.current[i] = el)} type="button" role="tab"
                  id={`lp-pv-tab-${v.id}`} aria-controls="lp-pv-panel" aria-selected={view === v.id}
                  tabIndex={view === v.id ? 0 : -1} onClick={() => setView(v.id)} onKeyDown={(e) => onKey(e, i)}>
                  <v.icon size={14} aria-hidden="true" />{v.label}
                </button>
              ))}
            </div>
            <p className="lp-pv__where">{current.title}</p>
            <span className="demo-label lp-pv__demo">Example data</span>
          </div>
          <div id="lp-pv-panel" role="tabpanel" aria-labelledby={`lp-pv-tab-${view}`} className="lp-pv__body" key={view}>
            {view === 'student' ? <StudentPreview /> : <LecturerPreview />}
          </div>
        </Reveal>
        <p className="lp-note lp-note--center">Illustrative example data. Not real students or results.</p>
      </div>
    </section>
  )
}
