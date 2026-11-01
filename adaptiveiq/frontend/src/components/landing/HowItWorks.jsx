import { BookOpen, ChartColumn, ListChecks, Sparkles } from 'lucide-react'
import { SectionHead } from './Reveal'
import { useInView } from './motion'

const STEPS = [
  { icon: BookOpen, title: 'Choose', text: 'Select a subject, topic, syllabus unit, or learning material.' },
  { icon: Sparkles, title: 'Generate', text: 'The configured AI model produces structured questions, which are checked automatically.' },
  { icon: ListChecks, title: 'Assess', text: 'Students attempt assigned assessments or personal practice quizzes.' },
  { icon: ChartColumn, title: 'Improve', text: 'Analytics identify learning gaps and recommend targeted revision.' },
]

export default function HowItWorks() {
  const [ref, inView] = useInView({ once: true, rootMargin: '0px 0px -15% 0px' })
  return (
    <section id="how" className="lp-section lp-section--band" aria-labelledby="lp-how-title">
      <div className="container">
        <SectionHead id="lp-how-title" eyebrow="How it works" title="Four steps, one loop."
          lead="Each quiz feeds the next one. What students get wrong shapes what they practise, and what lecturers revise." />
        <ol ref={ref} className={`lp-steps ${inView ? 'is-in' : ''}`}>
          <span className="lp-steps__rail" aria-hidden="true"><span /></span>
          {STEPS.map((s, i) => (
            <li key={s.title} className="lp-step" style={{ '--i': i }}>
              <span className="lp-step__node"><s.icon size={18} aria-hidden="true" /></span>
              <p className="lp-step__n">Step {i + 1}</p>
              <h3 className="lp-h3">{s.title}</h3>
              <p className="lp-step__text">{s.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
