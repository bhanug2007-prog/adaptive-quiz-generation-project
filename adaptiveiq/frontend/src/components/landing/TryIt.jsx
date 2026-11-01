import { GraduationCap, Terminal, UserRound } from 'lucide-react'
import Reveal, { SectionHead } from './Reveal'
import UiText from './UiText'
import { TRY_LECTURER, TRY_STUDENT } from './guideData'

function Script({ icon: Icon, title, steps }) {
  return (
    <Reveal className="lp2-script">
      <h3 className="lp-h3 lp2-script__title"><Icon size={18} aria-hidden="true" />{title}</h3>
      <ol className="lp2-script__list">
        {steps.map((s) => <li key={s}><UiText text={s} /></li>)}
      </ol>
    </Reveal>
  )
}

/** A short test script for each role, and a tip for filling a local copy with labelled demo data. */
export default function TryIt() {
  return (
    <section id="try" className="lp-section lp2-section" aria-labelledby="lp2-try-title">
      <div className="container">
        <SectionHead id="lp2-try-title" eyebrow="Try it yourself" title="Test it step by step."
          lead="Use two browsers, or a normal and a private window: one for the lecturer, one for the student." />
        <div className="lp2-scripts">
          <Script icon={GraduationCap} title="As a lecturer" steps={TRY_LECTURER} />
          <Script icon={UserRound} title="As a student" steps={TRY_STUDENT} />
        </div>
        <Reveal className="lp2-tip">
          <h3 className="lp-h3 lp2-script__title"><Terminal size={17} aria-hidden="true" />Running your own local copy?</h3>
          <p>
            You can fill it with a demo course so the analytics have something to show. In the <code>backend</code> folder run{' '}
            <code>python -m scripts.seed_demo</code>. It adds a course marked “demo data” with hand-written, reviewed
            questions and 12 demo students whose answers are simulated, not real. Sign in as{' '}
            <code>demo.lecturer@demo.example.com</code> or <code>demo.student01@demo.example.com</code> with the
            password <code>DemoPass123</code>. These accounts exist only in a local database you seed yourself.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
