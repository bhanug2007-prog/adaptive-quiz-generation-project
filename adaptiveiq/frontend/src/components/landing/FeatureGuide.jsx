import { SectionHead } from './Reveal'
import UiText from './UiText'

function FeatureCard({ f, prefix }) {
  const Icon = f.icon
  return (
    <li id={`${prefix}-${f.id}`} className="lp2-card">
      <div className="lp2-card__head">
        <span className={`lp2-card__icon lp2-card__icon--${prefix}`}><Icon size={18} aria-hidden="true" /></span>
        <h3 className="lp-h3">{f.title}</h3>
        {f.note && <span className="lp2-card__note">{f.note}</span>}
      </div>
      <dl className="lp2-card__body">
        <div><dt>What it does</dt><dd><UiText text={f.what} /></dd></div>
        <div><dt>How it works</dt><dd><UiText text={f.how} /></dd></div>
        <div>
          <dt>Try it</dt>
          <dd>
            <ol className="lp2-card__try">
              {f.try.map((t) => <li key={t}><UiText text={t} /></li>)}
            </ol>
          </dd>
        </div>
      </dl>
    </li>
  )
}

/** One portal's features as cards: what it does, how it works, and the clicks to try it. */
export default function FeatureGuide({ id, prefix, eyebrow, title, lead, features, band }) {
  return (
    <section id={id} className={`lp-section lp2-section ${band ? 'lp-section--band' : ''}`} aria-labelledby={`${id}-title`}>
      <div className="container">
        <SectionHead id={`${id}-title`} eyebrow={eyebrow} title={title} lead={lead} />
        <ul className="lp2-cards">
          {features.map((f) => <FeatureCard key={f.id} f={f} prefix={prefix} />)}
        </ul>
      </div>
    </section>
  )
}
