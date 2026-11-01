import { forwardRef } from 'react'
import { Check, Sparkles, TrendingUp } from 'lucide-react'
import Ring from './Ring'

const SCORES = [52, 58, 55, 66, 71, 78]

/**
 * Floating quiz cards arranged in CSS 3D space. Purely illustrative,
 * so it is hidden from assistive tech and described in one sentence instead.
 */
const HeroCards = forwardRef(function HeroCards(_, ref) {
  return (
    <figure className="lp-cards" aria-label="Illustration of an AdaptiveIQ practice question, a topic mastery ring and a score trend, using example data.">
      <div ref={ref} className="lp-cards__stage" aria-hidden="true">
        {/* stack of quiz cards behind the question */}
        <div className="lp-fcard lp-fcard--ghost lp-fcard--g2" />
        <div className="lp-fcard lp-fcard--ghost lp-fcard--g1" />

        {/* question card */}
        <div className="lp-fcard lp-fcard--question">
          <div className="lp-fq__top">
            <span className="lp-chip lp-chip--accent"><Sparkles size={11} />AI-generated practice</span>
            <span className="lp-fq__count">Question 4 of 10</span>
          </div>
          <p className="lp-fq__topic">Probability · Medium</p>
          <p className="lp-fq__text">A fair die is rolled twice. What is the probability that the two rolls sum to 7?</p>
          <ul className="lp-fq__opts">
            <li><b>A</b>1/12</li>
            <li className="is-right"><b>B</b>1/6<Check size={14} /></li>
            <li><b>C</b>5/36</li>
            <li><b>D</b>7/36</li>
          </ul>
          <p className="lp-fq__why">6 of the 36 equally likely outcomes sum to 7, so 6/36 = 1/6.</p>
        </div>

        {/* mastery ring */}
        <div className="lp-fcard lp-fcard--mastery">
          <p className="lp-fcard__label">Topic mastery</p>
          <div className="lp-fm__row">
            <Ring value={72} size={64} stroke={6} />
            <div>
              <p className="lp-fm__topic">Conditional probability</p>
              <p className="lp-fm__meta">Likely range 61–81</p>
              <p className="lp-fm__meta">8 answered · 6 correct</p>
            </div>
          </div>
        </div>

        {/* performance */}
        <div className="lp-fcard lp-fcard--perf">
          <div className="lp-fp__head">
            <p className="lp-fcard__label">Last 6 quizzes</p>
            <span className="lp-fp__trend"><TrendingUp size={12} />Improving</span>
          </div>
          <div className="lp-fp__bars">
            {SCORES.map((s, i) => <span key={i} style={{ '--h': `${s}%`, '--i': i }} />)}
          </div>
        </div>

        {/* generation status */}
        <div className="lp-fcard lp-fcard--gen">
          <span className="lp-gen-dot" />
          <span>Validating questions</span>
          <span className="lp-gen-count">7 / 10</span>
        </div>
      </div>
      <figcaption className="lp-cards__cap">Illustration · example data</figcaption>
    </figure>
  )
})

export default HeroCards
