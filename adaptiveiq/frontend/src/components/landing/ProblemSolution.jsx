import { ArrowRight } from 'lucide-react'
import Reveal, { SectionHead } from './Reveal'

const PAIRS = [
  {
    problem: 'Students receive marks but do not know precisely which concepts they misunderstand.',
    answer: 'Topic-level analytics',
    detail: 'Every answer is tied to a topic, so a result becomes a per-topic picture: what is solid, what is shaky, what was skipped, and what to revise next.',
    tone: 'teal',
  },
  {
    problem: 'Lecturers spend time creating quizzes and manually interpreting results.',
    answer: 'AI-generated assessments',
    detail: 'Draft questions from a topic or your own material, check them, edit them, approve them. Class results arrive already grouped by topic and question.',
    tone: 'accent',
  },
  {
    problem: 'Traditional fixed-difficulty quizzes do not automatically respond to each learner’s progress.',
    answer: 'Adaptive practice',
    detail: 'Practice difficulty moves one level at a time from each student’s current estimate, and weak topics come back on a spaced revision schedule.',
    tone: 'teal',
  },
]

export default function ProblemSolution() {
  return (
    <section className="lp-section" aria-labelledby="lp-problem-title">
      <div className="container">
        <SectionHead id="lp-problem-title" eyebrow="Why AdaptiveIQ"
          title="Assessment should do more than produce a score."
          lead="A mark tells you how a quiz went. It rarely tells you what to do next. AdaptiveIQ connects each question to a topic, so the result can." />
        <ol className="lp-problems">
          {PAIRS.map((p, i) => (
            <Reveal as="li" key={p.answer} delay={i * 80} className="lp-problem">
              <div className="lp-problem__q">
                <span className="lp-problem__n">0{i + 1}</span>
                <p>{p.problem}</p>
              </div>
              <div className={`lp-problem__a lp-tone-${p.tone}`}>
                <p className="lp-problem__ans"><ArrowRight size={15} aria-hidden="true" />{p.answer}</p>
                <p className="lp-problem__detail">{p.detail}</p>
              </div>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  )
}
