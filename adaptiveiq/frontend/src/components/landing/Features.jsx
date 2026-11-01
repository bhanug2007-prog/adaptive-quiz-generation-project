import { ChartColumn, ClipboardCheck, Gauge, ScanSearch, SlidersHorizontal, Sparkles, Target, Users } from 'lucide-react'
import Reveal, { SectionHead } from './Reveal'

const FEATURES = [
  { icon: Sparkles, tone: 'accent', title: 'AI Quiz Generation',
    text: 'Generate structured multiple-choice questions from a subject, topic, difficulty, question count, and optional reference material.' },
  { icon: Target, tone: 'teal', title: 'Personalized Practice',
    text: 'Help students practise topics selected from their syllabus or identified from their own learning history.' },
  { icon: Gauge, tone: 'teal', title: 'Topic Mastery Intelligence',
    text: 'Estimate proficiency from correctness, question difficulty and attempt history, with the evidence behind every estimate.' },
  { icon: ScanSearch, tone: 'neutral', title: 'Weak-Area Detection',
    text: 'Identify concepts where a student or a class repeatedly struggles, using rules you can read.' },
  { icon: SlidersHorizontal, tone: 'teal', title: 'Adaptive Difficulty',
    text: 'Adjust future question difficulty with an explicit, testable rule: one level up or down at a time.' },
  { icon: ChartColumn, tone: 'neutral', title: 'Learning Analytics',
    text: 'Score trends, topic-level performance, skipped questions kept separate from wrong ones, and next steps.' },
  { icon: Users, tone: 'neutral', title: 'Lecturer Insights',
    text: 'Class-wide strengths, frequently missed questions, and students who may need additional support.' },
  { icon: ClipboardCheck, tone: 'accent', title: 'AI-Assisted Assessment Creation',
    text: 'Draft questions, review answers, edit content, and approve every question before a quiz is published.' },
]

export default function Features() {
  return (
    <section id="features" className="lp-section" aria-labelledby="lp-features-title">
      <div className="container">
        <SectionHead id="lp-features-title" eyebrow="Product"
          title="Everything between a topic and a revision plan."
          lead="Question generation, assessment, and learning analytics in one place, built so each number can be traced back to answers." />
        <ul className="lp-features">
          {FEATURES.map((f, i) => (
            <Reveal as="li" key={f.title} delay={(i % 4) * 60} className={`lp-feature lp-tone-${f.tone}`}>
              <span className="lp-feature__icon"><f.icon size={18} aria-hidden="true" /></span>
              <h3 className="lp-h3">{f.title}</h3>
              <p>{f.text}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}
