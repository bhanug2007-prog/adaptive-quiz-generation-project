import { Sparkles } from 'lucide-react'
import Reveal, { SectionHead } from './Reveal'
import { HOW_STEPS } from './guideData'

/** The loop end to end in five plain steps, plus one honest paragraph on where AI is used. */
export default function GuideHow() {
  return (
    <section id="how" className="lp-section lp2-section lp-section--band" aria-labelledby="lp2-how-title">
      <div className="container">
        <SectionHead id="lp2-how-title" eyebrow="How it works" title="From a new course to a clear picture of learning."
          lead="Five steps. Each submitted quiz feeds the next one." />
        <ol className="lp2-steps">
          {HOW_STEPS.map((s, i) => (
            <li key={s.title} className="lp2-step">
              <span className="lp2-step__n num" aria-hidden="true">{i + 1}</span>
              <div>
                <h3 className="lp-h3">{s.title}</h3>
                <p>{s.text}</p>
              </div>
            </li>
          ))}
        </ol>
        <Reveal id="model" className="lp2-ai">
          <h3 className="lp-h3 lp2-ai__title"><Sparkles size={17} aria-hidden="true" />Where AI is used</h3>
          <p>
            Questions are drafted by a Qwen2.5-7B model that the team fine-tuned for multiple-choice questions. The model
            only writes questions. Automatic checks screen each one, but checks cannot prove a question is correct, so a
            lecturer must approve every question before students see it in an assessment. Practice quizzes that students
            make for themselves are labelled AI-generated and not lecturer-reviewed. Mastery, weak areas, difficulty and
            recommendations come from separate, open rules that never call the language model; so far they have been
            tested in simulations, not yet with real students.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
