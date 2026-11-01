import { useEffect, useState } from 'react'
import { Cpu, FlaskConical, ShieldCheck } from 'lucide-react'
import Reveal, { SectionHead } from './Reveal'
import { useInView, usePageVisible, useReducedMotion } from './motion'

const PIPELINE = [
  { group: 'gen', title: 'Qwen2.5-7B question generation', text: 'A fine-tuned language model drafts multiple-choice questions for the chosen topic and difficulty.' },
  { group: 'gen', title: 'Question validation', text: 'Automatic checks reject malformed, duplicated or give-away questions before anyone sees them.' },
  { group: 'ana', title: 'Student responses', text: 'Answers, skips and time taken are stored per question, per topic.' },
  { group: 'ana', title: 'Performance features', text: 'Accuracy, recency, difficulty and attempt history are computed for each student and topic.' },
  { group: 'ana', title: 'Topic mastery estimation', text: 'A Beta-Bernoulli estimate with an 80% likely range and an evidence label.' },
  { group: 'ana', title: 'Weak-area detection', text: 'Transparent rules flag topics with a low estimate, or a clear recent decline, once there is enough evidence.' },
  { group: 'ana', title: 'Adaptive recommendation', text: 'Next practice topic and difficulty, one level at a time, plus spaced revision dates.' },
  { group: 'ana', title: 'Feedback and evaluation', text: 'New answers update the estimates, and question quality is reviewed from real answers.' },
]

const CHECKS = [
  'Structure: exactly four distinct options and one answer key',
  'Duplicate detection against the question set',
  'Give-away check: the stem must not reveal the answer',
  'Explanation and answer key must agree on numbers',
  'Grounding against your reference text, when you supply it',
  'Numeric answers recomputed with a Python check',
]

/* Team's own pilot comparison. AI-assisted grading (not human), small samples; shown with their sizes. */
const RESULTS = [
  { name: 'FLAN-T5', ok: 3, n: 27 },
  { name: 'Qwen2.5 1.5B', ok: 16, n: 30 },
  { name: 'Qwen2.5 3B', ok: 18, n: 30 },
  { name: 'Qwen2.5 7B base', ok: 26, n: 30 },
  { name: 'Qwen2.5 7B fine-tuned', ok: 24, n: 30, ours: true },
]

function Pipeline() {
  const reduced = useReducedMotion()
  const visible = usePageVisible()
  const [ref, inView] = useInView({ rootMargin: '-10% 0px' })
  const [active, setActive] = useState(0)
  const running = inView && visible && !reduced
  useEffect(() => {
    if (!running) return undefined
    const id = setInterval(() => setActive((a) => (a + 1) % PIPELINE.length), 1800)
    return () => clearInterval(id)
  }, [running])
  return (
    <div ref={ref} className={`lp-pipe ${running ? 'is-running' : ''}`}>
      <div className="lp-pipe__groups" aria-hidden="true">
        <span className="lp-pipe__group lp-pipe__group--gen">Question generation · language model</span>
        <span className="lp-pipe__group lp-pipe__group--ana">Learning analytics · no language model</span>
      </div>
      <ol className="lp-pipe__list">
        {PIPELINE.map((s, i) => (
          <li key={s.title} className={`lp-pipe__step lp-pipe--${s.group} ${running && i === active ? 'is-active' : ''}`}
            onMouseEnter={() => setActive(i)}>
            <span className="lp-pipe__idx num" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
            <h3 className="lp-pipe__title">
              {s.title}
              <span className="visually-hidden">{s.group === 'gen' ? ' (question generation)' : ' (learning analytics)'}</span>
            </h3>
            <p className="lp-pipe__text">{s.text}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}

export default function ModelSection() {
  return (
    <section id="model" className="lp-section" aria-labelledby="lp-model-title">
      <div className="container">
        <SectionHead id="lp-model-title" eyebrow="AI & analytics"
          title="From generated questions to measurable learning insights."
          lead="Two separate parts. A language model writes questions. A transparent statistical model, which never uses the language model, turns answers into mastery estimates and recommendations." />

        <Reveal><Pipeline /></Reveal>

        <div className="lp-model-grid">
          <Reveal className="lp-mcard">
            <p className="lp-mcard__kicker"><Cpu size={14} aria-hidden="true" />The question model</p>
            <h3 className="lp-h3">Fine-tuned Qwen2.5-7B-Instruct</h3>
            <dl className="lp-spec">
              <div><dt>Architecture</dt><dd>Decoder-only Transformer LLM</dd></div>
              <div><dt>Fine-tuning</dt><dd>LoRA adapter, merged into the base weights</dd></div>
              <div><dt>Format</dt><dd>GGUF, Q4_K_M quantisation, about 4.7 GB</dd></div>
              <div><dt>Serving</dt><dd>llama.cpp <code>llama-server</code>, OpenAI-compatible endpoint</dd></div>
              <div><dt>Validation loss</dt><dd className="num">0.86 → 0.81 during fine-tuning</dd></div>
            </dl>
            <p className="lp-dim lp-small">The model runs on a server. Nothing is loaded in your browser.</p>
          </Reveal>

          <Reveal className="lp-mcard" delay={80}>
            <p className="lp-mcard__kicker"><ShieldCheck size={14} aria-hidden="true" />Checked before anyone sees it</p>
            <h3 className="lp-h3">Every generated question is validated</h3>
            <ul className="lp-checks lp-checks--one lp-checks--tight">
              {CHECKS.map((c) => <li key={c}><span className="lp-tick" aria-hidden="true" />{c}</li>)}
            </ul>
            <p className="lp-dim lp-small">Questions that fail are regenerated a limited number of times. Lecturers still approve every assessment question.</p>
          </Reveal>
        </div>

        <Reveal className="lp-mcard lp-results">
          <div className="lp-results__head">
            <div>
              <p className="lp-mcard__kicker"><FlaskConical size={14} aria-hidden="true" />Pilot comparison</p>
              <h3 className="lp-h3">Questions graded usable in a small pilot</h3>
              <p className="lp-dim lp-results__sub">Team’s own pilot set · grading was AI-assisted, not done by people</p>
            </div>
            <span className="lp-chip lp-chip--warn">Preliminary · AI-assisted grading</span>
          </div>
          <ul className="lp-bars" aria-label="Questions graded usable by model, preliminary AI-assisted grading">
            {RESULTS.map((r) => (
              <li key={r.name} className={r.ours ? 'is-ours' : ''}>
                <span className="lp-bars__name">{r.name}</span>
                <span className="lp-bars__track"><span style={{ '--w': `${(r.ok / r.n) * 100}%` }} /></span>
                <span className="lp-bars__val num">{r.ok} / {r.n}</span>
              </li>
            ))}
          </ul>
          <div className="lp-results__notes">
            <p>
              On a wider set of 90 inputs, the fine-tuned 7B model had <b className="num">67 / 90</b> questions graded usable.
              Formula-heavy topics were the weak spot, at <b className="num">9 / 18</b>.
            </p>
            <p>
              Preliminary, AI-assisted grading of 30 to 90 questions. On the shared 30 the base 7B model did slightly better
              than the fine-tuned one, so these numbers do not show that fine-tuning helped. A blind, human-graded comparison of
              base and fine-tuned models on held-out topics is part of the evaluation plan.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
