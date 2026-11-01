/* Static previews of real AdaptiveIQ screens, drawn with the app's own labels and layout.
   Sample content only: nothing here is fetched, and the buttons are not interactive. */
import { CalendarDays, Check, ChevronLeft, ChevronRight, Clock, Cpu, FlaskConical, Flag, ListChecks, Lock, Pencil, RefreshCw, RotateCcw, X } from 'lucide-react'

const OPTIONS = [
  ['A', 'Pages'],
  ['B', 'Frames'],
  ['C', 'Segments'],
  ['D', 'Partitions'],
]

/** Wraps a preview: the figure is described once for screen readers, the drawing itself is hidden. */
export function Preview({ label, path, className = '', children }) {
  return (
    <figure className={`mk ${className}`} aria-label={label} role="img">
      <div aria-hidden="true">
        {path && (
          <div className="mk__bar">
            <span className="mk__crumb">{path}</span>
          </div>
        )}
        <div className="mk__body">{children}</div>
      </div>
    </figure>
  )
}

function Pill({ tone = 'plain', icon: Icon, children }) {
  return <span className={`mk-pill mk-pill--${tone}`}>{Icon && <Icon size={12} strokeWidth={2} />}{children}</span>
}

function Btn({ tone = 'quiet', icon: Icon, iconRight: IconR, children }) {
  return <span className={`mk-btn mk-btn--${tone}`}>{Icon && <Icon size={13} strokeWidth={2} />}{children}{IconR && <IconR size={13} strokeWidth={2} />}</span>
}

function Bar({ value, max, tone = 'accent' }) {
  return <span className={`mk-progress mk-progress--${tone}`}><span style={{ width: `${(value / max) * 100}%` }} /></span>
}

/** Student quiz player: one question, four options, difficulty, progress and timer. */
export function QuizMock({ selected = 'B', detailed = false }) {
  return (
    <div className="mk-quiz">
      <div className="mk-quiz__top">
        <div>
          <p className="mk-kicker">Operating Systems · Memory Management</p>
          <p className="mk-title">Quiz 2: Deadlocks and memory</p>
        </div>
        <span className="mk-timer"><Clock size={13} strokeWidth={2} />12:40</span>
      </div>
      <div className="mk-quiz__progress">
        <Bar value={6} max={18} />
        <span className="mk-faint">6 of 18 answered</span>
      </div>
      <div className="mk-quiz__card">
        <div className="mk-row mk-row--between">
          <span className="mk-qnum">Question 7 <span className="mk-faint">of 18</span></span>
          <Pill tone="calm">Easy</Pill>
        </div>
        <p className="mk-question">In paging, what are the fixed-size blocks of physical memory called?</p>
        <ol className="mk-options">
          {OPTIONS.map(([l, t]) => (
            <li key={l} data-selected={l === selected || undefined}>
              <span className="mk-letter">{l}</span>{t}
              {l === selected && <Check size={14} strokeWidth={2.2} className="mk-options__tick" />}
            </li>
          ))}
        </ol>
        <div className="mk-row mk-row--between mk-quiz__nav">
          <Btn icon={ChevronLeft}>Previous</Btn>
          {detailed && <Btn icon={Flag}>Flag for review</Btn>}
          <Btn tone="solid" iconRight={ChevronRight}>Next</Btn>
        </div>
      </div>
    </div>
  )
}

/** The full player with the question navigator, for the showcase. */
export function PlayerMock() {
  const states = ['a', 'a', 'a', 'a', 'f', 'a', 'c', 'n', 'n', 'n', 'n', 'n', 'n', 'n', 'n', 'n', 'n', 'n']
  return (
    <div className="mk-player">
      <QuizMock detailed />
      <div className="mk-nav">
        <p className="mk-label">Questions</p>
        <div className="mk-nav__grid">
          {states.map((s, i) => (
            <span key={i} className={`mk-nav__btn mk-nav__btn--${s}`}>{i + 1}{s === 'f' && <Flag size={8} strokeWidth={2.4} />}</span>
          ))}
        </div>
        <ul className="mk-legend">
          <li><span className="mk-dot mk-dot--a" />Answered</li>
          <li><span className="mk-dot mk-dot--n" />Not answered</li>
          <li><Flag size={10} strokeWidth={2.4} />Flagged</li>
        </ul>
        <span className="mk-btn mk-btn--teal mk-btn--block">Submit quiz</span>
      </div>
    </div>
  )
}

export function ReviewCard({ n, status, difficulty, text, options, keyLetter, checks, actions }) {
  return (
    <div className={`mk-review ${status === 'Needs review' ? 'mk-review--open' : ''}`}>
      <div className="mk-row mk-row--wrap">
        <span className="mk-qnum">Q{n}</span>
        <Pill tone={status === 'Approved' ? 'ok' : 'warn'}>{status}</Pill>
        <Pill>{difficulty}</Pill>
        <span className="mk-faint">Memory Management</span>
        <Pill tone="accent" icon={Cpu}>AI-generated</Pill>
      </div>
      <p className="mk-question mk-question--sm">{text}</p>
      <ol className="mk-options mk-options--grid">
        {options.map(([l, t]) => (
          <li key={l} data-correct={l === keyLetter || undefined}>
            <span className="mk-letter">{l}</span>{t}
            {l === keyLetter && <span className="mk-key"><Check size={12} strokeWidth={2.4} />Correct answer</span>}
          </li>
        ))}
      </ol>
      {checks && (
        <dl className="mk-checks">
          {checks.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      )}
      {actions && (
        <div className="mk-row mk-row--wrap mk-review__actions">
          <Btn tone="ok" icon={Check}>Approve</Btn>
          <Btn icon={Pencil}>Edit</Btn>
          <Btn icon={RefreshCw}>Regenerate</Btn>
          <Btn tone="danger" icon={X}>Reject</Btn>
        </div>
      )}
    </div>
  )
}

/** Lecturer quiz review: approved and still-to-review questions with their automatic checks. */
export function ReviewMock() {
  return (
    <div className="mk-stack">
      <div className="mk-row mk-row--between mk-row--wrap">
        <div>
          <p className="mk-kicker">Operating Systems · Memory Management</p>
          <p className="mk-title">Paging basics</p>
        </div>
        <span className="mk-faint">3 of 5 questions approved</span>
      </div>
      <ReviewCard n={4} status="Needs review" difficulty="Medium"
        text="A system has a 32-bit logical address space and 4 KB pages. How many entries does a single-level page table need?"
        options={[['A', '2^12'], ['B', '2^16'], ['C', '2^20'], ['D', '2^32']]} keyLetter="C"
        checks={[['Calculation check', 'Python check agrees with the key'], ['Closest existing question', '18% shared wording (TF-IDF, not meaning)']]}
        actions />
      <ReviewCard n={3} status="Approved" difficulty="Easy"
        text="Which type of fragmentation does paging eliminate?"
        options={[['A', 'Internal fragmentation'], ['B', 'External fragmentation'], ['C', 'Both'], ['D', 'Neither']]} keyLetter="B" />
    </div>
  )
}

const TOPICS = [
  { subject: 'Operating Systems', topic: 'Memory Management', label: 'Developing', tone: 'warn', score: 63, lo: 42, hi: 85, ev: '6 questions answered: 4 correct, 2 wrong', next: 'Keep practising at the current level.' },
  { subject: 'Operating Systems', topic: 'Process Synchronization', label: 'Needs improvement', tone: 'bad', score: 38, lo: 19, hi: 60, ev: '7 questions answered: 2 correct, 5 wrong', next: 'Revise the concept, then practise with easier questions.' },
  { subject: 'Operating Systems', topic: 'CPU Scheduling', label: 'Insufficient evidence', tone: 'none', score: null, ev: '3 questions answered: 2 correct, 1 wrong', next: 'Answer at least 2 more different questions on this topic before judging mastery.' },
]

/** Student "My Progress": topic mastery with the evidence behind each estimate. */
export function MasteryMock({ count = 3, compact = false }) {
  return (
    <div className="mk-mastery">
      {TOPICS.slice(0, count).map((t) => (
        <div key={t.topic} className="mk-topic">
          <div className="mk-row mk-row--between">
            <span className="mk-faint">{t.subject}</span>
            <span className={`mk-status mk-status--${t.tone}`}><span className="mk-dot" />{t.label}</span>
          </div>
          <p className="mk-topic__name">{t.topic}</p>
          {t.score != null ? (
            <>
              <p className="mk-score"><strong>{t.score}</strong>/100 <span className="mk-faint">likely {t.lo}–{t.hi}</span></p>
              <span className={`mk-range mk-range--${t.tone}`}>
                <span className="mk-range__band" style={{ left: `${t.lo}%`, width: `${t.hi - t.lo}%` }} />
                <span className="mk-range__dot" style={{ left: `${t.score}%` }} />
              </span>
            </>
          ) : (
            <p className="mk-score mk-score--none">Insufficient evidence for an estimate</p>
          )}
          {compact ? <p className="mk-faint mk-topic__ev">{t.ev}</p> : (
            <dl className="mk-checks mk-checks--topic">
              <div><dt>Evidence</dt><dd>{t.ev}</dd></div>
              <div><dt>Next step</dt><dd>{t.next}</dd></div>
            </dl>
          )}
        </div>
      ))}
    </div>
  )
}

/** Lecturer "Create quiz": choose the topic, size and difficulty. */
export function CreateMock() {
  return (
    <div className="mk-stack mk-create">
      <div className="mk-field"><span className="mk-label">Subject</span><span className="mk-input">Operating Systems</span></div>
      <div className="mk-field"><span className="mk-label">Topic</span><span className="mk-input">CPU Scheduling</span></div>
      <div className="mk-row mk-create__pair">
        <div className="mk-field"><span className="mk-label">Number of questions</span><span className="mk-input">5</span></div>
        <div className="mk-field"><span className="mk-label">Marks per question</span><span className="mk-input">1</span></div>
      </div>
      <div className="mk-field">
        <span className="mk-label">Difficulty</span>
        <span className="mk-seg">
          <span>Easy</span><span>Medium</span><span>Hard</span><span data-on>Mixed</span>
        </span>
      </div>
      <span className="mk-btn mk-btn--solid mk-btn--block"><ListChecks size={13} strokeWidth={2} />Generate questions</span>
    </div>
  )
}

/** A finished generation run: every question passed its checks and waits for review. */
export function GeneratedMock() {
  const qs = [
    ['Easy', 'Which policy needs the burst length in advance?'],
    ['Medium', 'Which metric does shortest job first minimise?'],
    ['Hard', 'What happens to response time when the quantum shrinks?'],
    ['Easy', 'Which scheduler can starve long jobs?'],
    ['Medium', 'What problem does aging solve?'],
  ]
  return (
    <div className="mk-stack">
      <div className="mk-row mk-row--between">
        <span className="mk-qnum">Questions ready</span>
        <span className="mk-faint">5/5 passed checks</span>
      </div>
      <Bar value={5} max={5} tone="ok" />
      <ul className="mk-list">
        {qs.map(([d, t], i) => (
          <li key={t}>
            <span className="mk-list__n">Q{i + 1}</span>
            <span className="mk-list__t">{t}</span>
            <Pill>{d}</Pill>
          </li>
        ))}
      </ul>
      <span className="mk-btn mk-btn--solid mk-btn--block">Review 5 questions</span>
    </div>
  )
}

/** Lecturer class view: student × topic mastery heatmap. */
export function HeatmapMock() {
  const topics = ['Scheduling', 'Memory', 'Deadlocks', 'Sync']
  const rows = [
    ['Student 01', [72, 63, 81, null]],
    ['Student 02', [44, 58, 39, 51]],
    ['Student 03', [88, 76, null, 66]],
    ['Student 04', [35, 47, 52, 29]],
  ]
  const tone = (v) => (v == null ? 'none' : v >= 70 ? 'ok' : v >= 50 ? 'mid' : 'low')
  return (
    <div className="mk-heat">
      <span />
      {topics.map((t) => <span key={t} className="mk-heat__head">{t}</span>)}
      {rows.map(([name, vals]) => (
        <div key={name} className="mk-heat__row">
          <span className="mk-heat__name">{name}</span>
          {vals.map((v, i) => <span key={i} className={`mk-heat__cell mk-heat__cell--${tone(v)}`}>{v ?? '–'}</span>)}
        </div>
      ))}
      <ul className="mk-heat__legend">
        <li><span className="mk-heat__key mk-heat__cell--low" />Needs improvement</li>
        <li><span className="mk-heat__key mk-heat__cell--mid" />Developing</li>
        <li><span className="mk-heat__key mk-heat__cell--ok" />Proficient</li>
        <li><span className="mk-heat__key mk-heat__cell--none" />Not attempted</li>
      </ul>
    </div>
  )
}


const PAGE_TABLE_Q = {
  n: 4, status: 'Needs review', difficulty: 'Medium',
  text: 'A system has a 32-bit logical address space and 4 KB pages. How many entries does a single-level page table need?',
  options: [['A', '2^12'], ['B', '2^16'], ['C', '2^20'], ['D', '2^32']], keyLetter: 'C',
}

/** Lecturer quiz page: one question still to review, and publishing locked until all are approved. */
export function ApprovalMock() {
  return (
    <div className="mk-stack">
      <ReviewCard {...PAGE_TABLE_Q} actions />
      <div className="mk-publish">
        <div>
          <p className="mk-qnum">4 of 5 questions approved</p>
          <p className="mk-faint">Publishing unlocks when every question is approved.</p>
        </div>
        <span className="mk-btn mk-btn--solid mk-btn--off"><Lock size={12} strokeWidth={2.2} />Publish to students</span>
      </div>
    </div>
  )
}

const NEXT = [
  { topic: 'Process Synchronization', label: 'Needs improvement', tone: 'bad', why: 'Revise the concept, then practise with easier questions.', action: 'Practise easy' },
  { topic: 'Memory Management', label: 'Developing', tone: 'warn', why: 'Keep practising at the current level.', action: 'Practise medium' },
  { topic: 'CPU Scheduling', label: 'Insufficient evidence', tone: 'none', why: 'Answer at least 2 more different questions on this topic before judging mastery.', action: null },
]

/** Learning Insights: each topic's next practice level, with the rule-based reason. */
export function AdaptiveMock({ count = 3 }) {
  return (
    <ul className="mk-next">
      {NEXT.slice(0, count).map((t) => (
        <li key={t.topic}>
          <div className="mk-row mk-row--between mk-row--wrap">
            <span className="mk-topic__name">{t.topic}</span>
            <span className={`mk-status mk-status--${t.tone}`}><span className="mk-dot" />{t.label}</span>
          </div>
          <p className="mk-next__why">{t.why}</p>
          {t.action && <span className="mk-btn mk-btn--teal mk-btn--xs"><FlaskConical size={12} strokeWidth={2} />{t.action}</span>}
        </li>
      ))}
    </ul>
  )
}

const BARS = [
  ['CPU Scheduling', 74, 'Proficient', 'ok'],
  ['Memory Management', 63, 'Developing', 'warn'],
  ['Deadlocks', 55, 'Developing', 'warn'],
  ['Process Synchronization', 38, 'Needs improvement', 'bad'],
]

/** My Progress, condensed: mastery estimate per topic. */
export function AnalyticsMock() {
  return (
    <div className="mk-stack">
      <div className="mk-row mk-row--between">
        <span className="mk-qnum">Operating Systems</span>
        <span className="mk-faint">Mastery estimate</span>
      </div>
      <ul className="mk-bars">
        {BARS.map(([t, v, label, tone]) => (
          <li key={t}>
            <span className="mk-row mk-row--between">
              <span className="mk-bars__t">{t}</span>
              <span className={`mk-status mk-status--${tone}`}>{label}</span>
            </span>
            <span className="mk-bars__line">
              <span className={`mk-bars__track mk-bars__track--${tone}`}><span style={{ width: `${v}%` }} /></span>
              <span className="mk-bars__v">{v}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Learning Insights: spaced revision of missed questions. */
export function RevisionMock() {
  const due = [
    ['Which condition is not required for a deadlock?', 'Process Synchronization · box 1 · 1 review'],
    ['What does the TLB cache?', 'Memory Management · box 2 · 2 reviews'],
  ]
  return (
    <div className="mk-stack">
      <div className="mk-row mk-row--between mk-row--top">
        <div>
          <p className="mk-title">Spaced revision</p>
          <p className="mk-faint">A missed question returns after 1 day, then 3, 7, 14 and 30 days after each correct answer.</p>
        </div>
        <span className="mk-btn mk-btn--teal"><RotateCcw size={12} strokeWidth={2} />Start revision (2)</span>
      </div>
      <p className="mk-kicker">Due now (2)</p>
      <ul className="mk-qlist">
        {due.map(([q, meta]) => (
          <li key={q}><RotateCcw size={13} strokeWidth={2} /><span><span className="mk-qlist__q">{q}</span><span className="mk-faint">{meta}</span></span></li>
        ))}
      </ul>
      <p className="mk-kicker">Upcoming (1)</p>
      <ul className="mk-qlist">
        <li><CalendarDays size={13} strokeWidth={2} /><span><span className="mk-qlist__q">Which policy can starve long jobs?</span><span className="mk-faint">CPU Scheduling · due in 3 days</span></span></li>
      </ul>
    </div>
  )
}
