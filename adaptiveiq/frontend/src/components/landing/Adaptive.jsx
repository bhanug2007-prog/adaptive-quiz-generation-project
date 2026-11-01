import { Check, TrendingUp } from 'lucide-react'
import Reveal, { SectionHead } from './Reveal'
import Ring from './Ring'

const BENEFITS = [
  'Understand topic-wise strengths and weaknesses',
  'Practise independently without waiting for a lecturer',
  'Review mistakes with explanations',
  'Receive personalised revision suggestions',
  'Track progress over multiple attempts',
  'Prepare for exams using selected syllabus topics',
  'Review skipped and previously incorrect questions',
  'Revisit weak concepts through spaced revision',
]

const LEITNER = [1, 3, 7, 14, 30]
const LEVELS = ['Easy', 'Medium', 'Hard']

function EstimateCard() {
  return (
    <div className="lp-est">
      <div className="lp-est__head">
        <p className="lp-est__topic">Conditional probability</p>
        <span className="demo-label">Example data</span>
      </div>
      <div className="lp-est__main">
        <Ring value={72} size={104} stroke={8} caption="of 100" label="Estimated mastery 72 out of 100" />
        <dl className="lp-est__facts">
          <div><dt>Likely range (80%)</dt><dd className="num">61 – 81</dd></div>
          <div><dt>Evidence</dt><dd>8 questions answered, 6 correct</dd></div>
          <div><dt>Not counted as wrong</dt><dd>1 skipped, shown separately</dd></div>
        </dl>
      </div>
      <div className="lp-est__range" aria-hidden="true">
        <span className="lp-est__band" style={{ left: '61%', width: '20%' }} />
        <span className="lp-est__point" style={{ left: '72%' }} />
      </div>
      <div className="lp-est__foot">
        <div className="lp-est__pill"><span className="lp-evi" data-level="moderate"><i /><i /><i /></span>Limited evidence</div>
        <div className="lp-est__pill lp-est__pill--teal"><TrendingUp size={13} aria-hidden="true" />Improving: last 3 correct</div>
      </div>
      <p className="lp-est__next"><b>Next:</b> 5 questions at Hard difficulty to firm up the estimate.</p>
    </div>
  )
}

export default function Adaptive() {
  return (
    <section id="adaptive" className="lp-section" aria-labelledby="lp-adaptive-title">
      <div className="container">
        <SectionHead id="lp-adaptive-title" eyebrow="For students · Adaptive learning"
          title="Practice that responds to where you are."
          lead="AdaptiveIQ keeps an estimate for every topic you study and is honest about how sure it is. Practice and revision follow from it." />

        <div className="lp-split">
          <Reveal className="lp-split__a">
            <ul className="lp-checks">
              {BENEFITS.map((b) => <li key={b}><Check size={15} aria-hidden="true" />{b}</li>)}
            </ul>
            <p className="lp-note">
              Practice quizzes are ready straight away and are clearly labelled <em>AI-generated, not lecturer-reviewed</em>.
              Assessments your lecturer sets are reviewed question by question.
            </p>
          </Reveal>
          <Reveal className="lp-split__b" delay={100}>
            <EstimateCard />
          </Reveal>
        </div>

        <ul className="lp-explain">
          <Reveal as="li" className="lp-explain__item">
            <h3 className="lp-h3">An estimate, not a verdict</h3>
            <p>Mastery is a Beta-Bernoulli estimate. Recent answers and harder questions count for more, and every score comes with an 80% likely range.</p>
            <div className="lp-mini-rings" aria-hidden="true">
              <Ring value={81} size={44} stroke={4} color="var(--m-proficient)" />
              <Ring value={56} size={44} stroke={4} color="var(--m-developing)" />
              <Ring value={38} size={44} stroke={4} color="var(--m-needs)" />
            </div>
          </Reveal>
          <Reveal as="li" className="lp-explain__item" delay={60}>
            <h3 className="lp-h3">Evidence before scores</h3>
            <p>Under 5 different questions, a topic is labelled <em>insufficient evidence</em> instead of being given a score that looks more certain than it is.</p>
            <div className="lp-evi-scale" aria-hidden="true">
              {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <span key={n} className={n < 5 ? 'is-low' : ''}>{n}</span>)}
            </div>
          </Reveal>
          <Reveal as="li" className="lp-explain__item" delay={120}>
            <h3 className="lp-h3">One step at a time</h3>
            <p>Practice difficulty moves up or down by one level from your current estimate. No sudden jumps from easy to hard.</p>
            <div className="lp-levels" aria-hidden="true">
              {LEVELS.map((l, i) => <span key={l} style={{ '--i': i }}>{l}</span>)}
            </div>
          </Reveal>
          <Reveal as="li" className="lp-explain__item" delay={180}>
            <h3 className="lp-h3">Spaced revision</h3>
            <p>Topics come back on Leitner intervals. Get it right and the gap grows; miss it and the topic returns sooner.</p>
            <ol className="lp-leitner" aria-label="Revision intervals in days">
              {LEITNER.map((d) => <li key={d}><span className="num">{d}</span>{d === 1 ? 'day' : 'days'}</li>)}
            </ol>
          </Reveal>
        </ul>
        <p className="lp-note">
          Weak areas come from transparent rules on the estimate, the evidence and the recent trend, so each flag can be explained.
          Clustering methods such as K-Means are deliberately not used.
        </p>
      </div>
    </section>
  )
}
