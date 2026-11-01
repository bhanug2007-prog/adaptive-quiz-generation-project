import { GraduationCap, UserRound } from 'lucide-react'
import { SectionHead } from './Reveal'
import Reveal from './Reveal'
import { LECTURER_FEATURES, STUDENT_FEATURES } from './guideData'

function Column({ icon: Icon, title, href, items, prefix }) {
  return (
    <Reveal className="lp2-over__col">
      <h3 className="lp-h3 lp2-over__title"><Icon size={18} aria-hidden="true" />{title}</h3>
      <ul className="lp2-over__list">
        {items.map((f) => <li key={f.id}><a href={`#${prefix}-${f.id}`}>{f.title}</a></li>)}
      </ul>
      <a className="lp2-over__more" href={href}>See how each one works</a>
    </Reveal>
  )
}

/** The whole product at a glance: the two parts of the web app and what is in each. */
export default function GuideOverview() {
  return (
    <section id="features" className="lp-section lp2-section" aria-labelledby="lp2-over-title">
      <div className="container">
        <SectionHead id="lp2-over-title" eyebrow="What is inside" title="Two parts: one for students, one for lecturers."
          lead="Everything below is in the web app today. Each feature further down says what it does, how it works, and the exact clicks to try it." />
        <div className="lp2-over">
          <Column icon={UserRound} title="Student part" href="#adaptive" items={STUDENT_FEATURES} prefix="s" />
          <Column icon={GraduationCap} title="Lecturer part" href="#lecturers" items={LECTURER_FEATURES} prefix="l" />
        </div>
      </div>
    </section>
  )
}
